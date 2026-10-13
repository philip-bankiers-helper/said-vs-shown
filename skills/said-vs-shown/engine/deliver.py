#!/usr/bin/env python3
"""deliver.py — turn a rendered master into an episode's deliverables, then QA them.

usage: deliver.py <episode_dir> --master <rendered.mp4> [--poster-at SECONDS] [--repo-url URL]
                  [--max-mb 15] [--lufs -16] [--no-companion] [--unreviewed]

Refuses to run until edit/episode.json has "reviewed_by" (the stage 10 review). --unreviewed makes a draft
delivery anyway; its disclosure then reads "not yet human-reviewed".

Writes only into <episode_dir>/deliver/:
  <slug>.mp4          the master, loudness-normalized (engine/loudfix.sh when present, else inline two-pass loudnorm)
  <slug>-web.mp4      720p two-pass H.264 cut under --max-mb (bitrate from the duration, with a safety margin)
  poster.jpg          frame at the end of the first "squeeze" scene (or scene 1), or at --poster-at
  captions.vtt/.srt   copies of video/audio/captions.*
  transcript.md       script lines with their start times (audio/script.json + audio/timeline.json)
  SOURCES.md          story sources, other leads and the source map (episode.json, leads.json, sources.json)
  chapters.txt        YouTube-style chapters (episode.json "chapters" + the timeline)
  companion/          the static companion page (companion.py), with the web cut and poster copied in
QA gates (exit 1 if any fails): duration matches the timeline, integrated loudness within 1 LU of the target,
true peak <= -1 dBTP, web cut size, captions present, and the flash check: the most large luminance jumps
(>= 10% of the luma range, frame to frame, whole-frame signalstats YAVG) inside any 1-second window must be
<= 3 (WCAG 2.3.1 three-flashes threshold, read conservatively). ffmpeg's two-pass logs go to a temp dir.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import companion as C  # noqa: E402

AUDIO_KBPS = 128
SAFETY = 0.94          # leave 6% of the size cap for container overhead and rate-control drift
MAX_VIDEO_KBPS = 3000  # no point exceeding this at 720p for slide-like motion graphics
JUMP = 0.10 * 219      # 10% of the 8-bit limited luma range (16-235)


def die(msg):
    sys.exit(f'deliver.py: {msg}')


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        die(f'command failed ({r.returncode}): {" ".join(cmd[:6])} ...\n{r.stderr.strip()[-1500:]}')
    return r


def duration(f):
    r = run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f])
    return float(r.stdout.strip())


def loudness(f, target=-16.0):
    """Measure with loudnorm (first pass). Returns the JSON dict (input_i, input_tp, input_lra, ...)."""
    r = run(['ffmpeg', '-hide_banner', '-nostats', '-i', f, '-af',
             f'loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'])
    m = re.findall(r'\{[^{}]*"input_i"[^{}]*\}', r.stderr, re.S)
    if not m:
        die(f'could not measure loudness of {f}')
    return json.loads(m[-1])


def normalize(master, out, target, cfg):
    """engine/loudfix.sh (config.json target) when present and the target is the configured one; else inline."""
    script = os.path.join(HERE, 'loudfix.sh')
    tp = float(cfg.get('true_peak', -1.5))
    if os.path.isfile(script) and float(cfg.get('lufs', -16)) == target:
        run(['sh', script, master, out])
        return 'loudfix.sh'
    m = loudness(master, target)
    af = (f"loudnorm=I={target}:TP={tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    run(['ffmpeg', '-y', '-loglevel', 'error', '-i', master, '-c:v', 'copy', '-af', af, '-ar', '48000',
         '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out])
    return 'two-pass loudnorm'


def web_cut(src, out, dur, max_bytes):
    kbps = int(max_bytes * 8 * SAFETY / dur / 1000 - AUDIO_KBPS)
    kbps = min(kbps, MAX_VIDEO_KBPS)
    if kbps < 150:
        die(f'{dur:.0f}s does not fit {max_bytes / 1e6:.0f} MB at a watchable 720p bitrate (would be {kbps} kbps)')
    for attempt in range(2):
        with tempfile.TemporaryDirectory(prefix='svs-2pass-') as td:
            log = os.path.join(td, 'x264')
            common = ['-vf', 'scale=-2:720:flags=lanczos', '-c:v', 'libx264', '-preset', 'slow', '-profile:v', 'high',
                      '-pix_fmt', 'yuv420p', '-b:v', f'{kbps}k', '-passlogfile', log]
            run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, *common, '-pass', '1', '-an', '-f', 'mp4', os.devnull], cwd=td)
            run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, *common, '-pass', '2', '-c:a', 'aac',
                 '-b:a', f'{AUDIO_KBPS}k', '-ar', '48000', '-movflags', '+faststart', os.path.abspath(out)], cwd=td)
        size = os.path.getsize(out)
        if size <= max_bytes:
            return kbps, size
        kbps = int(kbps * max_bytes / size * 0.95)   # rate control overshot: one retry, scaled down
    return kbps, size


def flash_check(f):
    """Max count of large frame-to-frame luma jumps within any 1-second window (signalstats YAVG)."""
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', f, '-an', '-vf',
                        'scale=320:-2,signalstats,metadata=mode=print:key=lavfi.signalstats.YAVG:file=-',
                        '-f', 'null', '-'], capture_output=True, text=True)
    if r.returncode != 0:
        die(f'signalstats failed on {f}: {r.stderr.strip()[-500:]}')
    ts, ys, t = [], [], None
    for line in r.stdout.splitlines():
        m = re.search(r'pts_time:([\d.]+)', line)
        if m:
            t = float(m.group(1))
            continue
        m = re.match(r'lavfi\.signalstats\.YAVG=([\d.]+)', line)
        if m and t is not None:
            ts.append(t); ys.append(float(m.group(1)))
    jumps = [ts[i] for i in range(1, len(ys)) if abs(ys[i] - ys[i - 1]) >= JUMP]
    worst, at, j = 0, None, 0
    for i, t0 in enumerate(jumps):
        while jumps[j] < t0 - 1.0 + 1e-9:
            j += 1
        if i - j + 1 > worst:
            worst, at = i - j + 1, jumps[j]
    return worst, at, len(jumps), len(ys)


def write(path, text):
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)


def main(argv):
    opts = {'max_mb': 15.0, 'poster_at': None, 'repo_url': None, 'master': None, 'lufs': None, 'companion': True,
            'unreviewed': False}
    args = []
    it = iter(argv)
    for a in it:
        if a == '--master':
            opts['master'] = next(it, None)
        elif a == '--poster-at':
            opts['poster_at'] = float(next(it, '0'))
        elif a == '--repo-url':
            opts['repo_url'] = next(it, None)
        elif a == '--max-mb':
            opts['max_mb'] = float(next(it, '15'))
        elif a == '--lufs':
            opts['lufs'] = float(next(it, '-16'))
        elif a == '--no-companion':
            opts['companion'] = False
        elif a == '--unreviewed':
            opts['unreviewed'] = True
        elif a in ('-h', '--help'):
            print(__doc__.strip())
            sys.exit(0)
        else:
            args.append(a)
    if len(args) != 1 or not opts['master']:
        die('usage: deliver.py <episode_dir> --master <rendered.mp4> [--poster-at S] [--repo-url URL] [--max-mb 15] [--lufs -16] '
            '[--no-companion] [--unreviewed]')
    ep = os.path.abspath(args[0])
    master = os.path.abspath(opts['master'])
    if not os.path.isfile(master):
        die(f'master not found: {master}')
    for tool in ('ffmpeg', 'ffprobe'):
        if not shutil.which(tool):
            die(f'{tool} is not on PATH')
    cfg = C.config()
    target = opts['lufs'] if opts['lufs'] is not None else float(cfg.get('lufs', -16))
    E = C.load_episode(ep)
    if not str(E.get('reviewed_by') or '').strip():
        if not opts['unreviewed']:
            die('edit/episode.json has no "reviewed_by": the user reviews the episode first (SKILL.md stage 10). '
                'Pass --unreviewed for a draft delivery (its disclosure says "not yet human-reviewed").')
        print('deliver.py: warning: no reviewed_by; draft delivery, disclosure reads "not yet human-reviewed"', file=sys.stderr)
    V = os.path.join(ep, 'video')
    tl = C.read_json(os.path.join(V, 'audio', 'timeline.json'))
    scfg = C.read_json(os.path.join(V, 'scenes.json'))
    scenes = scfg['scenes']
    script = C.read_json(os.path.join(V, 'audio', 'script.json'))
    leads = C.read_json(os.path.join(ep, 'ledger', 'leads.json'), default=[])
    srcmap = C.sources_map(ep)
    slug = C.slug_of(E)
    show, edition, window = E.get('show') or C.TOOL_NAME, E.get('edition', ''), E.get('window', '')
    D = os.path.join(ep, 'deliver')
    os.makedirs(D, exist_ok=True)
    final, web = os.path.join(D, f'{slug}.mp4'), os.path.join(D, f'{slug}-web.mp4')
    if os.path.abspath(final) == master:
        die(f'--master is the output path {final}; pass the render instead')
    max_bytes = int(opts['max_mb'] * 1_000_000)

    # 1. loudness-normalized master
    print(f'[1/6] loudness -> {os.path.relpath(final, ep)}', flush=True)
    how = normalize(master, final, target, cfg)
    dur = duration(final)

    # 2. web cut
    print(f'[2/6] web cut -> {os.path.relpath(web, ep)}', flush=True)
    kbps, web_size = web_cut(final, web, dur, max_bytes)

    # 3. poster: end of the first squeeze beat
    bounds = [0.0] + list(tl.get('cuts', [])) + [tl['total'] + scfg.get('hold', 0.12)]
    if opts['poster_at'] is not None:
        poster_t = opts['poster_at']
    else:
        i = next((k for k, s in enumerate(scenes) if s['id'] == 'squeeze'), 0)
        poster_t = bounds[i + 1] - 0.4 if i + 1 < len(bounds) else 1.0
    poster_t = max(0.0, min(poster_t, dur - 0.1))
    print(f'[3/6] poster at {poster_t:.2f}s', flush=True)
    run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{poster_t:.3f}', '-i', final, '-frames:v', '1',
         '-vf', 'scale=1280:-2', '-q:v', '3', os.path.join(D, 'poster.jpg')])

    # 4. captions + text deliverables
    print('[4/6] captions, transcript.md, SOURCES.md, chapters.txt', flush=True)
    captions_ok = True
    for ext in ('vtt', 'srt'):
        src = os.path.join(V, 'audio', f'captions.{ext}')
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(D, f'captions.{ext}'))
        else:
            captions_ok = False
            print(f'deliver.py: missing {src} (run captions.py)', file=sys.stderr)

    head = ', '.join(x for x in (show, edition, window) if x)
    starts = {ln['id']: ln['start'] for ln in tl.get('lines', [])}
    tr = [f'# Transcript — {head}', '']
    for ln in script.get('lines', []):
        t = starts.get(ln['id'])
        tr += [(f'**{C.mmss(t)}** — ' if t is not None else '') + ln['text'], '']
    write(os.path.join(D, 'transcript.md'), '\n'.join(tr))

    overrides = E.get('lead_badge_overrides') or {}
    src_lines = [f'# Sources — {head}', '']
    src_lines.append((f'All sources captured {E["captured"]}. ' if E.get('captured') else '') +
                     'Badges: Checked = headline visible in a primary source; Company = rests on the company\'s/authors\' '
                     'own account; Reported = secondary only; Provider = discovery provider only; Older = background.')
    for s in E.get('stories', []):
        meta = ', '.join(x for x in (C.BADGE_WORD[C.badge_key(s.get('badge'))], s.get('date', '')) if x)
        src_lines += ['', f'## {s.get("n", "")} {s.get("topic", "")} ({meta})']
        src_lines += [f'- {x["label"]}: {x["url"]}' for x in s.get('sources', [])]
    if leads:
        src_lines += ['', '## Other leads (companion page)']
        for l in sorted(leads, key=C.lead_sort_key):
            urls = ' '.join(srcmap[i] for i in l.get('source_ids', []) if i in srcmap)
            word = C.BADGE_WORD[C.lead_badge_key(l, overrides)]
            src_lines.append(f'- {C.lead_num(l)} {l["title"]} [{word}] — {l.get("one_liner", "")}' + (f' {urls}' if urls else ''))
    if srcmap:
        src_lines += ['', '## Source map']
        src_lines += [f'- {k} {v}' for k, v in srcmap.items()]
    write(os.path.join(D, 'SOURCES.md'), '\n'.join(src_lines) + '\n')

    chapters = C.chapters_of(E, scenes, tl, need_zero=True)
    write(os.path.join(D, 'chapters.txt'), ''.join(f'{C.mmss(t)} {label.replace(" · ", " ")}\n' for t, label in chapters))

    # 5. companion page
    info = None
    if opts['companion']:
        print('[5/6] companion -> deliver/companion/', flush=True)
        info = C.build(ep, os.path.join(D, 'companion'), video_name=os.path.basename(web), repo_url=opts['repo_url'])

    # 6. QA
    print('[6/6] QA', flush=True)
    m = loudness(final, target)
    lufs, tp = float(m['input_i']), float(m['input_tp'])
    worst, worst_at, n_jumps, n_frames = flash_check(final)
    expected = round(tl['total'] + scfg.get('hold', 0.12), 2)
    gates = [
        ('duration', abs(dur - expected) <= 0.5, f'{C.mmss(dur)} ({dur:.2f}s; timeline {expected:.2f}s)'),
        ('loudness', abs(lufs - target) <= 1.0, f'{lufs:.1f} LUFS integrated (target {target:.0f}, via {how})'),
        ('true peak', tp <= -1.0, f'{tp:.1f} dBTP (max -1.0)'),
        ('web size', web_size <= max_bytes, f'{web_size / 1e6:.2f} MB (cap {max_bytes / 1e6:.0f} MB, video {kbps} kbps)'),
        ('captions', captions_ok, 'captions.vtt + captions.srt' if captions_ok else 'missing'),
        ('flashes', worst <= 3, f'max {worst} large luminance jump(s) in 1 s' + (f' at {worst_at:.2f}s' if worst_at is not None else '')
         + f' ({n_jumps} total over {n_frames} frames; WCAG 2.3.1 <= 3)'),
    ]
    print(f'\nQA — {slug}')
    for name, ok, detail in gates:
        print(f'  {"PASS" if ok else "FAIL"}  {name:<10} {detail}')
    if info:
        print(f'  ----  companion  {info["chapters"]} chapters · {info["cues"]} cues · {info["lead_cards"]} other leads · '
              f'{info["leads_reviewed"]} leads reviewed · {info["stories"]} stories · {info["sources"]} sources captured · '
              f'{info["claims"]} claims traced')
    print(f'  ----  files      {os.path.relpath(D, ep)}/: ' + ', '.join(sorted(os.listdir(D))))
    failed = [n for n, ok, _ in gates if not ok]
    if failed:
        print(f'\nFAILED: {", ".join(failed)}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
