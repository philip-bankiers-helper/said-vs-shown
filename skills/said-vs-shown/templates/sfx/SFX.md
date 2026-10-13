# Sound marks

Three short marks, synthesized from deterministic ffmpeg expressions (sine bursts, and pink noise with a fixed seed). No samples or third-party recordings are involved, so they carry the repository's license (MIT). The same ffmpeg version and command produce the same bytes. They were made with ffmpeg 8.1.1.

| File | Length | Peak | Use (frame.md → Sound) |
|---|---|---|---|
| `click-soft.wav` | 0.12 s | −8.3 dBFS | a boundary drawing, a slot filling |
| `pop.wav` | 0.15 s | −9.1 dBFS | a card landing |
| `whoosh-short.wav` | 0.50 s | −8.0 dBFS | the squeeze, a camera move into a story |

All three are 48 kHz, mono, 16-bit PCM, peaking well below 0 dBFS (no clipping). Mix them at volume 0.2–0.35 under narration.

## Commands

Run from this folder.

```sh
# click-soft.wav: two decaying sine partials (1750 Hz + 820 Hz), band-limited, 2 ms attack, 30 ms tail fade
ffmpeg -y -f lavfi -i "aevalsrc='0.28*sin(2*PI*1750*t)*exp(-70*t)+0.18*sin(2*PI*820*t)*exp(-45*t)':d=0.12:s=48000" \
  -af "highpass=f=250,lowpass=f=7000,afade=t=in:d=0.002,afade=t=out:st=0.09:d=0.03" \
  -ar 48000 -ac 1 -c:a pcm_s16le click-soft.wav

# pop.wav: a sine whose pitch falls from 900 Hz to 260 Hz (phase = integral of 260 + 640*exp(-32t)), fast attack, exponential decay
ffmpeg -y -f lavfi -i "aevalsrc='0.4*(1-exp(-900*t))*exp(-24*t)*sin(2*PI*(260*t+640*(1-exp(-32*t))/32))':d=0.15:s=48000" \
  -af "highpass=f=120,lowpass=f=5000,afade=t=out:st=0.11:d=0.04" \
  -ar 48000 -ac 1 -c:a pcm_s16le pop.wav

# whoosh-short.wav: seeded pink noise through a band-pass whose center sweeps 400 → 3600 → 700 Hz,
# shaped by a sin² swell envelope
ffmpeg -y -f lavfi -i "anoisesrc=d=0.5:c=pink:r=48000:a=1:seed=1013" \
  -f lavfi -i "aevalsrc='0.9*pow(sin(PI*t/0.5),2)*exp(-1.5*t)':d=0.5:s=48000" \
  -filter_complex "[0:a]asendcmd=c='0.00 bandpass f 400;0.05 bandpass f 700;0.10 bandpass f 1200;0.15 bandpass f 2000;0.20 bandpass f 3000;0.25 bandpass f 3600;0.30 bandpass f 3000;0.35 bandpass f 2000;0.40 bandpass f 1200;0.45 bandpass f 700',bandpass=f=400:width_type=q:w=0.9[n];[n][1:a]amultiply,volume=2.5,afade=t=out:st=0.44:d=0.06[o]" \
  -map "[o]" -ar 48000 -ac 1 -c:a pcm_s16le whoosh-short.wav
```

Check the levels with `ffmpeg -i <file> -af volumedetect -f null -`.
