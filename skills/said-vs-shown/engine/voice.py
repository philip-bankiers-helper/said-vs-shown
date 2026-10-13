#!/usr/bin/env python3
"""voice.py — script.json -> narration.wav + transcript + aligned words + captions + scene words, in one pass.

usage: voice.py <project_dir> [--only L2,L5] [--lenient]

Reads <project>/audio/script.json ({voice?, speed?, engine?, display, lines:[{id, scene, text, gap_after, speed?}]};
voice and speed default to engine/config.json).
1. Kokoro TTS per line through HyperFrames (pinned in config.json). Cached in audio/.tts-cache.json;
   the key is model + HyperFrames version + voice + speed + text, so a line is re-voiced only when one changes.
   --only L2,L5 re-voices exactly those lines (an id or its prefix before "-") and freezes the rest:
   any other line whose take is stale or missing is an error instead of being re-voiced.
2. Mixes the takes on a timeline (0.35 s lead-in + per-line gap_after), loudnorm to the config target.
3. Transcribes the mix: Parakeet if installed, else Whisper small.en; transcript.json is always rewritten
   and the engine is recorded in timeline.json.
4. align.py (ASR timings on the script's words), captions.py (cues/VTT/SRT), scene_words.py.
Scene cuts sit 0.36 s before the first line of each new scene.
Writes audio/{Lnn.wav, timeline.json, narration.wav, transcript.json, words.json, cues.json,
captions.vtt, captions.srt, scene-words.json}.

Gates (strict by default, exit 1; --lenient only reports): words per minute outside config "wpm" on any
line longer than 8 words, a caption cue faster than "max_cps" or longer than "max_chars", and
integrated loudness more than 1 LU from "lufs".
Kokoro runs from $HYPERFRAMES_PYTHON if set, else $SVS_HOME/kokoro (see setup.sh).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ENGINE = os.path.dirname(os.path.abspath(__file__))
LEAD, CUT_BEFORE = 0.35, 0.36
DEFAULT_MODEL = 'kokoro-82m'


def die(msg):
    print('voice.py: ' + msg, file=sys.stderr)
    sys.exit(1)


def load_config():
    with open(os.path.join(ENGINE, 'config.json'), encoding='utf-8') as f:
        cfg = json.load(f)
    cfg['home'] = os.path.abspath(os.path.expanduser(os.environ.get('SVS_HOME') or cfg['home']))
    return cfg


def load_json(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def dump_json(obj, p, indent=1):
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=indent, ensure_ascii=False)


def run(cmd, what, **kw):
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', **kw)
    if r.returncode != 0:
        err = '\n'.join((r.stderr or '').strip().splitlines()[-15:])
        out = '\n'.join((r.stdout or '').strip().splitlines()[-3:])
        die('%s failed (exit %d)\n--- stderr ---\n%s\n--- stdout ---\n%s' % (what, r.returncode, err, out))
    return r


def last_json(text):
    for line in reversed((text or '').strip().splitlines()):
        line = line.strip()
        if line.startswith('{'):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def kokoro_env(cfg):
    env = dict(os.environ)
    if env.get('HYPERFRAMES_PYTHON'):
        return env
    for rel in (('bin', 'python'), ('Scripts', 'python.exe')):
        p = os.path.join(cfg['home'], 'kokoro', *rel)
        if os.path.exists(p):
            env['HYPERFRAMES_PYTHON'] = p
            return env
    print('voice.py: warning: no Kokoro venv in %s and HYPERFRAMES_PYTHON is unset; HyperFrames will look for a '
          'python with kokoro-onnx on PATH (run engine/setup.sh)' % os.path.join(cfg['home'], 'kokoro'), file=sys.stderr)
    return env


def media_duration(p):
    r = run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p], 'ffprobe ' + p)
    return float(r.stdout.strip())


def loudness(p):
    """Integrated loudness (LUFS) and true peak (dBTP) of a file, from ffmpeg's ebur128 summary."""
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', p, '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', errors='replace')
    summary = r.stderr[r.stderr.rfind('Summary:'):] if 'Summary:' in r.stderr else r.stderr
    i = re.findall(r'\bI:\s*(-?[\d.]+|-inf)\s*LUFS', summary)
    tp = re.findall(r'\bPeak:\s*(-?[\d.]+|-inf)\s*dBFS', summary)
    return (float(i[-1]) if i else None), (float(tp[-1]) if tp else None)


def matches_only(line_id, only):
    return any(line_id == o or line_id.startswith(o + '-') for o in only)


def main(argv=None):
    ap = argparse.ArgumentParser(description='script.json -> narration, words, captions, scene words')
    ap.add_argument('project')
    ap.add_argument('--only', default='', help='comma-separated line ids (or id prefixes) to re-voice; freeze the rest')
    ap.add_argument('--lenient', action='store_true', help='report gate failures instead of exiting 1')
    a = ap.parse_args(argv)

    cfg = load_config()
    npx = shutil.which('npx')  # npx.cmd on Windows
    if not npx:
        die('npx not found on PATH (install Node.js >= 22)')
    for tool in ('ffmpeg', 'ffprobe'):
        if not shutil.which(tool):
            die('%s not found on PATH' % tool)
    HF = [npx, '-y', 'hyperframes@%s' % cfg['hyperframes']]

    proj = os.path.abspath(a.project)
    A = os.path.join(proj, 'audio')
    s = load_json(os.path.join(A, 'script.json'))
    lines = s.get('lines') or die('script.json has no lines')
    ids = [L['id'] for L in lines]
    if len(set(ids)) != len(ids):
        die('duplicate line ids in script.json')
    only = [o.strip() for o in a.only.split(',') if o.strip()]
    unknown = [o for o in only if not any(matches_only(i, [o]) for i in ids)]
    if unknown:
        die('--only names no line: %s' % ', '.join(unknown))

    model = s.get('engine') or DEFAULT_MODEL
    voice = s.get('voice') or cfg['voice']
    base_speed = s.get('speed', cfg['speed'])
    env = kokoro_env(cfg)
    cache_p = os.path.join(A, '.tts-cache.json')
    cache = load_json(cache_p) if os.path.exists(cache_p) else {}

    # 1. TTS per line (cached); with --only, every other line must already have a fresh take
    plan, frozen_stale, voiced = [], [], []
    for L in lines:
        out = os.path.join(A, '%s.wav' % L['id'])
        spd = L.get('speed', base_speed)
        key = hashlib.sha256(('%s|hyperframes@%s|%s|%s|%s' % (model, cfg['hyperframes'], voice, spd, L['text']))
                             .encode('utf-8')).hexdigest()
        fresh = cache.get(L['id'], {}).get('key') == key and os.path.exists(out)
        if only and not matches_only(L['id'], only):
            if not fresh:
                frozen_stale.append(L['id'])
        elif only or not fresh:
            plan.append((L, out, spd, key))
    if frozen_stale:
        die('--only freezes lines whose take is stale or missing: %s (drop --only or add them)' % ', '.join(frozen_stale))
    for L, out, spd, key in plan:
        print('[tts] %s' % L['id'], file=sys.stderr)
        r = run(HF + ['tts', L['text'], '-v', voice, '-s', str(spd), '-o', out, '--json'], 'TTS for %s' % L['id'], env=env)
        res = last_json(r.stdout) or {}
        dur = res.get('durationSeconds') or media_duration(out)
        cache[L['id']] = {'key': key, 'dur': dur}
        dump_json(cache, cache_p)
        voiced.append(L['id'])

    # 2. timeline + mix + loudness
    t, tl = LEAD, []
    for L in lines:
        dur = cache[L['id']]['dur']
        n = len(L['text'].split())
        tl.append({'id': L['id'], 'scene': L['scene'], 'start': round(t, 3), 'dur': round(dur, 3), 'words': n,
                   'wpm': round(n / dur * 60) if dur else 0})
        t += dur + L.get('gap_after', 0.7)
    total = round(t, 3)
    cuts = [round(x['start'] - CUT_BEFORE, 2) for prev, x in zip(tl, tl[1:]) if x['scene'] != prev['scene']]
    scenes = [tl[0]['scene']] + [x['scene'] for prev, x in zip(tl, tl[1:]) if x['scene'] != prev['scene']]
    timeline = {'lead_in': LEAD, 'lines': tl, 'cuts': cuts, 'scenes': scenes, 'total': total,
                'tts': {'model': model, 'voice': voice, 'hyperframes': cfg['hyperframes']}}
    tl_p = os.path.join(A, 'timeline.json')
    dump_json(timeline, tl_p)

    narration = os.path.join(A, 'narration.wav')
    inputs, filt = [], []
    for i, L in enumerate(tl):
        inputs += ['-i', os.path.join(A, '%s.wav' % L['id'])]
        ms = int(L['start'] * 1000)
        filt.append('[%d:a]aresample=48000,adelay=%d|%d[a%d]' % (i, ms, ms, i))
    filt.append(''.join('[a%d]' % i for i in range(len(tl))) +
                'amix=inputs=%d:normalize=0,apad=whole_dur=%s,atrim=0:%s,loudnorm=I=%s:TP=%s:LRA=11[out]'
                % (len(tl), total, total, cfg['lufs'], cfg['true_peak']))
    run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', *inputs, '-filter_complex', ';'.join(filt),
         '-map', '[out]', '-ar', '48000', '-ac', '1', narration], 'mixing narration.wav')
    lufs, true_peak = loudness(narration)

    # 3. transcription in a scratch dir (HyperFrames patches caption HTML under --dir), result always overwritten
    models = last_json(subprocess.run(HF + ['models', 'list', '--json'], stdin=subprocess.DEVNULL, capture_output=True,
                                      text=True, encoding='utf-8', errors='replace').stdout) or {}
    parakeet = any(m.get('engine') == 'parakeet' and m.get('installed') for m in models.get('models', []))
    engine_args = ['--engine', 'parakeet'] if parakeet else ['--engine', 'whisper', '--model', 'small.en']
    tmp = tempfile.mkdtemp(prefix='svs-asr-')
    try:
        r = run(HF + ['transcribe', narration, '--dir', tmp, *engine_args, '--json'], 'transcription (%s)' % engine_args[1])
        res = last_json(r.stdout) or {}
        if not res.get('ok'):
            die('transcription failed: %s' % (res.get('error') or r.stdout.strip()[-500:]))
        src = res.get('transcriptPath') or os.path.join(tmp, 'transcript.json')
        shutil.copyfile(src, os.path.join(A, 'transcript.json'))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    timeline['asr'] = {'engine': res.get('engine', engine_args[1]), 'model': res.get('model')}
    dump_json(timeline, tl_p)

    # 4. align, captions, scene words
    al = run([sys.executable, os.path.join(ENGINE, 'align.py'), os.path.join(A, 'script.json'),
              os.path.join(A, 'transcript.json'), tl_p, os.path.join(A, 'words.json')], 'align.py')
    cap = run([sys.executable, os.path.join(ENGINE, 'captions.py'), os.path.join(A, 'words.json'), A,
               '--cuts', ','.join(map(str, cuts)), '--display', os.path.join(A, 'script.json'),
               '--max-chars', str(cfg['max_chars']), '--max-cps', str(cfg['max_cps'])], 'captions.py')
    run([sys.executable, os.path.join(ENGINE, 'scene_words.py'), proj], 'scene_words.py')
    capq = json.loads(cap.stdout)

    # gates
    lo, hi = cfg['wpm']
    fails = []
    for x in tl:
        if x['words'] > 8 and not lo <= x['wpm'] <= hi:
            fails.append('wpm: %s speaks at %d wpm (allowed %d-%d); adjust its speed or text' % (x['id'], x['wpm'], lo, hi))
    for c in capq['violations']:
        fails.append('caption: "%s" at %.2fs is %d chars, %.1f chars/s (max %d chars, %s cps)'
                     % (c['text'], c['start'], len(c['text']), c['cps'], cfg['max_chars'], cfg['max_cps']))
    if lufs is None or abs(lufs - cfg['lufs']) > 1.0:
        fails.append('loudness: narration.wav is %s LUFS (target %s +/-1)' % (lufs, cfg['lufs']))

    print(json.dumps({'voiced': voiced, 'lines': tl, 'cuts': cuts, 'total': total,
                      'loudness': {'lufs': lufs, 'true_peak': true_peak}, 'asr': timeline['asr'],
                      'wer': json.loads(al.stdout), 'captions': {k: v for k, v in capq.items() if k != 'violations'},
                      'gates': {'mode': 'lenient' if a.lenient else 'strict', 'failures': fails}},
                     indent=1, ensure_ascii=False))
    if fails:
        print('voice.py: %d gate failure(s):\n  %s' % (len(fails), '\n  '.join(fails)), file=sys.stderr)
        return 0 if a.lenient else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
