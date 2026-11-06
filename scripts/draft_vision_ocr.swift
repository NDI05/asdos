import Foundation
import Vision
import AppKit

// Local-only draft OCR. Output contains student data and must stay private.
while let line = readLine() {
    let fields = line.split(separator: "\t", maxSplits: 1).map(String.init)
    guard fields.count == 2 else { continue }
    let pageID = fields[0], path = fields[1]
    var result: [String: Any] = ["page_id": pageID, "status": "needs_human_review", "engine": "apple-vision-local", "coordinate_origin": "bottom-left", "lines": []]
    do {
        guard let image = NSImage(contentsOfFile: path), let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { throw NSError(domain:"image", code:1) }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg).perform([request])
        result["lines"] = (request.results ?? []).compactMap { observation -> [String: Any]? in
            guard let candidate = observation.topCandidates(1).first else { return nil }
            let b = observation.boundingBox
            return ["text": candidate.string, "bbox_normalized": [b.minX, b.minY, b.maxX, b.maxY], "confidence_uncalibrated": candidate.confidence]
        }
    } catch { result["error"] = String(describing: type(of: error)) }
    if let data = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]), let json = String(data: data, encoding: .utf8) { print(json); fflush(stdout) }
}
