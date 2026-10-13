#!/usr/bin/env python3
"""scene_words.py — slice audio/words.json by the timeline's scene cuts into audio/scene-words.json.

usage: scene_words.py <project_dir> [--hold SECONDS]

Reads <project>/audio/{script.json, timeline.json, words.json}. Scene ids come from the script's
lines, in order (consecutive lines may share a scene; a scene may not reappear later). Scene i spans
[cut[i-1], cut[i]); the first starts at 0 and the last runs to total + hold, where hold is --hold,
else "hold" from <project>/scenes.json, else 0.12 (the same bounds assemble.py uses).
Each word goes to the scene of its script line and gets LOCAL times (seconds from the scene start):

  {"<scene>": {"global_start": 9.33, "duration": 11.35, "words": [{"t": "First,", "s": 0.19, "e": 0.91}]}}

Exits 1 when the scene count and the cut count disagree (scenes != cuts + 1).
"""
import argparse
import bisect
import json
import os
import sys

DEFAULT_HOLD = 0.12


def scene_order(lines):
    order = []
    for L in lines:
        sc = L['scene']
        if order and order[-1] == sc:
            continue
        if sc in order:
            raise ValueError('scene "%s" reappears after another scene; give each stretch its own scene id' % sc)
        order.append(sc)
    return order


def slice_words(script, timeline, words, hold=DEFAULT_HOLD):
    scenes = scene_order(script['lines'])
    cuts = list(timeline['cuts'])
    if len(scenes) != len(cuts) + 1:
        raise ValueError('%d scenes in script.json but %d cuts in timeline.json (need scenes = cuts + 1); '
                         're-run voice.py' % (len(scenes), len(cuts)))
    bounds = [0.0] + cuts + [timeline['total'] + hold]
    line_scene = {L['id']: L['scene'] for L in script['lines']}
    out = {}
    for i, sc in enumerate(scenes):
        out[sc] = {'global_start': round(bounds[i], 2), 'duration': round(bounds[i + 1] - bounds[i], 2), 'words': []}
    for w in words:
        sc = line_scene.get(w.get('line'))
        if sc is None:  # words without a script line: place by time
            sc = scenes[bisect.bisect_right(cuts, w['start'])]
        g0 = out[sc]['global_start']
        out[sc]['words'].append({'t': w['text'], 's': round(w['start'] - g0, 2), 'e': round(w['end'] - g0, 2)})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='slice words.json into per-scene local word times')
    ap.add_argument('project')
    ap.add_argument('--hold', type=float, default=None)
    a = ap.parse_args(argv)
    A = os.path.join(os.path.abspath(a.project), 'audio')
    loaded = []
    for name in ('script.json', 'timeline.json', 'words.json'):
        with open(os.path.join(A, name), encoding='utf-8') as f:
            loaded.append(json.load(f))
    hold = a.hold
    if hold is None:
        hold = DEFAULT_HOLD
        scenes_p = os.path.join(os.path.abspath(a.project), 'scenes.json')
        if os.path.exists(scenes_p):
            with open(scenes_p, encoding='utf-8') as f:
                hold = float(json.load(f).get('hold', DEFAULT_HOLD))
    try:
        out = slice_words(*loaded, hold=hold)
    except ValueError as e:
        print('scene_words.py: %s' % e, file=sys.stderr)
        return 1
    with open(os.path.join(A, 'scene-words.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(json.dumps({'scenes': len(out), 'words': sum(len(v['words']) for v in out.values()),
                      'out': 'audio/scene-words.json'}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
