// ocr-locate.swift — find a verbatim quote inside an existing screenshot with Apple Vision (on-device).
//
// macOS ONLY (Vision + AppKit). Optional tool: nothing else in the engine depends on it. On Linux or
// Windows, re-run receipt.mjs with --nojs 1 on the saved capture instead.
//
// Used when a page refuses headless Chrome (e.g. 403) but a legitimate capture already exists.
//
// usage: swift ocr-locate.swift <image.png> "<quote>"
// prints JSON: {found, image:{w,h}, lines:[{text,x,y,w,h}]}: pixel rects, top-left origin.
// exit 0 = found, 1 = not found, 2 = usage error / unreadable image / Vision failure.
import AppKit
import Foundation
import Vision

func emit(_ obj: [String: Any]) {
  if let data = try? JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .sortedKeys]),
    let s = String(data: data, encoding: .utf8)
  {
    print(s)
  }
}

let args = CommandLine.arguments
if args.count == 2 && (args[1] == "--help" || args[1] == "-h") {
  print("usage: swift ocr-locate.swift <image.png> \"<quote>\"")
  print("Finds a verbatim quote in a screenshot with Apple Vision (macOS only); prints JSON {found, image, lines}.")
  print("exit 0 = found, 1 = not found, 2 = usage error / unreadable image / Vision failure.")
  exit(0)
}
guard args.count >= 3, let img = NSImage(contentsOfFile: args[1]),
  let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil)
else {
  emit(["found": false, "error": "usage: swift ocr-locate.swift <image.png> \"<quote>\" (image must be readable)"])
  exit(2)
}
let quote = args[2]
let W = Double(cg.width), H = Double(cg.height)
func norm(_ s: String) -> String {
  s.lowercased().replacingOccurrences(of: "\u{2019}", with: "'").replacingOccurrences(of: "\u{2018}", with: "'")
    .components(separatedBy: CharacterSet.alphanumerics.inverted).filter { !$0.isEmpty }.joined(separator: " ")
}
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = false
do {
  try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
} catch {
  emit(["found": false, "error": "Vision failed: \(error.localizedDescription)"])
  exit(2)
}
let obs = (req.results ?? []).compactMap { o -> (String, CGRect)? in
  guard let t = o.topCandidates(1).first?.string else { return nil }
  let b = o.boundingBox
  return (t, CGRect(x: b.minX * W, y: (1 - b.maxY) * H, width: b.width * W, height: b.height * H))
}.sorted { $0.1.minY == $1.1.minY ? $0.1.minX < $1.1.minX : $0.1.minY < $1.1.minY }

// greedy: find consecutive OCR lines whose joined text contains the quote
let q = norm(quote)
var hit: [(String, CGRect)] = []
if !q.isEmpty {
  let qw = q.components(separatedBy: " ")
  outer: for i in obs.indices {
    // the quote must start on line i: line i holds the whole quote, is its opening, or ends with its first words
    let first = norm(obs[i].0)
    let starts = !first.isEmpty && (first.contains(q) || q.hasPrefix(first)
      || (1...qw.count).contains { n in
        let p = qw.prefix(n).joined(separator: " ")
        return first == p || first.hasSuffix(" " + p)
      })
    if !starts { continue }
    var acc = ""
    for j in i..<min(obs.count, i + 4) {
      acc += (acc.isEmpty ? "" : " ") + norm(obs[j].0)
      if acc.contains(q) || (q.hasPrefix(norm(obs[i].0)) && acc.hasPrefix(q)) || acc.hasSuffix(q) {
        hit = Array(obs[i...j])
        break outer
      }
      if !q.contains(norm(obs[j].0)) && j > i { break }
    }
  }
}
// trim the first/last line rects to the quote's share of characters (approximate horizontal extent)
var lines: [[String: Any]] = []
for (k, h) in hit.enumerated() {
  var r = h.1
  let t = norm(h.0)
  if k == 0,
    let rg = t.range(of: String(q.prefix(min(q.count, t.count))))
      ?? t.range(of: q.components(separatedBy: " ").prefix(3).joined(separator: " "))
  {
    let startFrac = Double(t.distance(from: t.startIndex, to: rg.lowerBound)) / Double(max(1, t.count))
    r = CGRect(x: r.minX + r.width * startFrac, y: r.minY, width: r.width * (1 - startFrac), height: r.height)
  }
  if k == hit.count - 1, let lastWord = q.components(separatedBy: " ").last,
    let rg = t.range(of: lastWord, options: .backwards)
  {
    let endFrac = Double(t.distance(from: t.startIndex, to: rg.upperBound)) / Double(max(1, t.count))
    r = CGRect(
      x: r.minX, y: r.minY, width: max(10, (h.1.maxX - h.1.minX) * endFrac - (r.minX - h.1.minX)), height: r.height)
  }
  lines.append(["text": h.0, "x": r.minX, "y": r.minY, "w": r.width, "h": r.height])
}
emit(["found": !hit.isEmpty, "image": ["w": W, "h": H], "lines": lines])
exit(hit.isEmpty ? 1 : 0)
