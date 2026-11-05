// 서류 이미지의 개인정보를 이 컴퓨터 안에서 찾아 검게 칠한다. 인식한 글자는 출력하거나 저장하지 않는다.
// 놓칠 수 있으므로 결과는 사람이 한 장씩 확인한다.
// 옆으로 눕거나 기울어진 쪽은 바로 세워 저장한다. 글자를 못 읽은 쪽은 저장하지 않는다.
// 실행: swift scripts/mask_documents.swift private/real_small private/real_masked
// 이름, 환자번호, 주민번호만 칠하려면 끝에 --basic을 붙인다.
import AppKit
import Foundation
import Vision

struct Line {
    let text: String
    let plain: String
    let box: CGRect
    let candidate: VNRecognizedText
}

let nameLabels = ["환자성명", "환자이름", "환자명", "수진자명", "수진자", "성명", "이름"]
let staffWords = ["의사", "의료인", "대표자", "담당", "약사", "발행인"]
let patientNoLabels = ["환자등록번호", "병원등록번호", "등록번호", "환자번호", "병록번호", "차트번호", "챠트번호", "환자ID", "등록No", "ChartNo"]
let patientNoExcluded = ["주민", "사업자", "요양기관", "면허", "승인"]
let residentLabels = ["주민등록번호", "주민번호"]
let contactLabels = ["전화번호", "연락처", "휴대폰", "승인번호", "카드번호"]
let addressExcluded = ["요양기관", "사업장", "소재지"]
let notValueWords = nameLabels + patientNoLabels + residentLabels + contactLabels + ["주소", "진료", "기간", "구분", "금액", "합계", "외래", "입원", "퇴원", "본인", "공단", "야간", "공휴일"]
let patterns = [
    "resident": #"(?<!\d)\d{6}\s*[-–—~]\s*[\d*xX●•]{1,7}"#,
    "phone": #"(?<!\d)0\d{1,2}[-). ]\s*\d{3,4}[-. ]\s*\d{4}(?!\d)"#,
    "card": #"(?<!\d)\d{4}[- ]?[\d*xX]{4}[- ]?[\d*xX]{4}[- ]?[\d*xX]{3,4}(?!\d)"#,
]

func plain(_ text: String) -> String {
    text.components(separatedBy: .whitespacesAndNewlines).joined()
}

func rotated(_ image: CGImage, by radians: CGFloat) -> CGImage {
    let w = CGFloat(image.width), h = CGFloat(image.height)
    let newW = Int((abs(cos(radians)) * w + abs(sin(radians)) * h).rounded())
    let newH = Int((abs(sin(radians)) * w + abs(cos(radians)) * h).rounded())
    let ctx = CGContext(data: nil, width: newW, height: newH, bitsPerComponent: 8, bytesPerRow: 0,
                        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: newW, height: newH))
    ctx.translateBy(x: CGFloat(newW) / 2, y: CGFloat(newH) / 2)
    ctx.rotate(by: radians)
    ctx.draw(image, in: CGRect(x: -w / 2, y: -h / 2, width: w, height: h))
    return ctx.makeImage()!
}

func read(_ image: CGImage) -> ([VNRecognizedTextObservation], [CGRect]) {
    let text = VNRecognizeTextRequest()
    text.recognitionLevel = .accurate
    text.recognitionLanguages = ["ko-KR", "en-US"]
    text.usesLanguageCorrection = false
    let codes = VNDetectBarcodesRequest()
    try! VNImageRequestHandler(cgImage: image, options: [:]).perform([text, codes])
    return (text.results ?? [], (codes.results ?? []).map { $0.boundingBox })
}

// 한글과 숫자를 믿을 만하게 많이 읽은 방향일수록 점수가 높다.
func readability(_ observations: [VNRecognizedTextObservation]) -> Float {
    observations.reduce(0) { sum, o in
        guard let c = o.topCandidates(1).first else { return sum }
        return sum + c.confidence * Float(c.string.filter { $0.isNumber || ("가"..."힣").contains($0) }.count)
    }
}

func tilt(_ observations: [VNRecognizedTextObservation], width: CGFloat, height: CGFloat) -> CGFloat {
    let angles = observations.filter { $0.boundingBox.width > 0.08 }.map { o -> CGFloat in
        atan2((o.topRight.y - o.topLeft.y) * height, (o.topRight.x - o.topLeft.x) * width)
    }.sorted()
    return angles.isEmpty ? 0 : angles[angles.count / 2]
}

func recognize(_ url: URL) -> (CGImage, [Line], [CGRect], Int) {
    let source = CGImageSourceCreateWithURL(url as CFURL, nil)!
    let original = CGImageSourceCreateImageAtIndex(source, 0, nil)!
    var best = original, bestDegrees = 0, bestScore: Float = -1
    for degrees in [0, 90, 180, 270] {
        let image = degrees == 0 ? original : rotated(original, by: CGFloat(degrees) * .pi / 180)
        let score = readability(read(image).0)
        if score > bestScore { best = image; bestDegrees = degrees; bestScore = score }
    }
    var (observations, codes) = read(best)
    let angle = tilt(observations, width: CGFloat(best.width), height: CGFloat(best.height))
    if abs(angle) > 0.003, abs(angle) < 0.35 {
        best = rotated(best, by: -angle)
        (observations, codes) = read(best)
    }
    let lines = observations.compactMap { o -> Line? in
        guard let c = o.topCandidates(1).first else { return nil }
        return Line(text: c.string, plain: plain(c.string), box: o.boundingBox, candidate: c)
    }
    return (best, lines, codes, bestDegrees)
}

func box(_ line: Line, _ range: Range<String.Index>) -> CGRect {
    (try? line.candidate.boundingBox(for: range))?.boundingBox ?? line.box
}

// 공백을 뺀 글자 위치를 원래 문자열의 위치로 바꾼다.
func originalRange(_ text: String, from start: Int, count: Int) -> Range<String.Index>? {
    let indices = text.indices.filter { !text[$0].isWhitespace }
    guard start >= 0, count > 0, start + count <= indices.count else { return nil }
    return indices[start]..<text.index(after: indices[start + count - 1])
}

func offset(of label: String, in text: String) -> Int? {
    text.range(of: label).map { text.distance(from: text.startIndex, to: $0.lowerBound) }
}

func neighbors(of label: Line, in lines: [Line]) -> [Line] {
    let h = label.box.height
    let right = lines.filter {
        abs($0.box.midY - label.box.midY) < h * 1.0 && $0.box.minX >= label.box.maxX - 0.005 && $0.box.minX - label.box.maxX < 0.3
    }.sorted { $0.box.minX < $1.box.minX }
    let below = lines.filter {
        $0.box.maxY <= label.box.minY + h * 0.3 && label.box.minY - $0.box.maxY < h * 6
            && $0.box.midX > label.box.minX - 0.05 && $0.box.midX < label.box.maxX + 0.05
    }.sorted { $0.box.maxY > $1.box.maxY }
    return Array(right.prefix(1)) + Array(below.prefix(1))
}

func isLabelLike(_ text: String) -> Bool {
    notValueWords.contains { text.contains($0) }
}

func isName(_ text: String) -> Bool {
    text.range(of: #"^[가-힣*]{2,5}$"#, options: .regularExpression) != nil && !isLabelLike(text)
}

func hasDigit(_ text: String) -> Bool {
    text.range(of: #"\d"#, options: .regularExpression) != nil
}

// 라벨 뒤 값이 같은 줄에 있으면 그 범위를, 없으면 옆이나 아래 칸을 돌려준다.
func findValue(_ label: String, _ line: Line, _ lines: [Line], _ valid: (String) -> Bool) -> (Line, Range<String.Index>)? {
    if let start = offset(of: label, in: line.plain) {
        let after = start + label.count
        let rest = String(line.plain.dropFirst(after)).trimmingCharacters(in: CharacterSet(charactersIn: ":： )]"))
        if !rest.isEmpty, valid(rest) {
            let skipped = line.plain.count - after - rest.count
            if let range = originalRange(line.text, from: after + skipped, count: rest.count) { return (line, range) }
        }
    }
    for other in neighbors(of: line, in: lines) where valid(other.plain) {
        return (other, other.text.startIndex..<other.text.endIndex)
    }
    return nil
}

func nameMask(_ line: Line, _ range: Range<String.Index>) -> CGRect {
    let whole = box(line, range)
    let count = max(line.text[range].filter { !$0.isWhitespace }.count, 2)
    let width = whole.width / CGFloat(count)
    let hidden = count <= 3 ? 1 : count - 2
    return CGRect(x: whole.minX + width - width * 0.08, y: whole.minY, width: width * (CGFloat(hidden) + 0.16), height: whole.height)
}

func documentKind(_ lines: [Line]) -> String {
    let all = lines.map { $0.plain }.joined()
    if all.contains("세부산정") || all.contains("세부내역") { return "세부내역서" }
    if all.contains("약제비") { return "약제비영수증" }
    if all.contains("처방전") { return "처방전" }
    if all.contains("납입확인") { return "납입확인서" }
    if all.contains("진단서") { return "진단서" }
    if all.contains("확인서") { return "확인서" }
    if all.contains("계산서") || all.contains("영수증") { return "영수증" }
    return "모름"
}

func isPatientNo(_ text: String) -> Bool {
    text.range(of: #"^[A-Za-z]{0,2}\d[\d-]{3,}$"#, options: .regularExpression) != nil
}

let basicOnly = CommandLine.arguments.contains("--basic")
let inputDir = URL(fileURLWithPath: CommandLine.arguments[1])
let outputDir = URL(fileURLWithPath: CommandLine.arguments[2])
try FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)
let files = try FileManager.default.contentsOfDirectory(at: inputDir, includingPropertiesForKeys: nil)
    .filter { $0.pathExtension.lowercased() == "png" }
    .sorted { $0.lastPathComponent < $1.lastPathComponent }

var pages: [(URL, CGImage, [Line], [CGRect], Int)] = []
for file in files {
    let (image, lines, codes, degrees) = recognize(file)
    pages.append((file, image, lines, codes, degrees))
}

// 환자 이름을 먼저 모아서, 라벨 없이 다시 나오는 곳도 칠한다.
var names = Set<String>()
var patientNumbers = Set<String>()
for (_, _, lines, _, _) in pages {
    for line in lines where patientNoLabels.contains(where: line.plain.contains) && !patientNoExcluded.contains(where: line.plain.contains) {
        guard let label = patientNoLabels.first(where: line.plain.contains) else { continue }
        if let (value, range) = findValue(label, line, lines, isPatientNo) {
            let found = plain(String(value.text[range]))
            if found.count >= 5 { patientNumbers.insert(found) }
        }
    }
    for line in lines where nameLabels.contains(where: line.plain.contains) && !staffWords.contains(where: line.plain.contains) {
        guard let label = nameLabels.first(where: line.plain.contains) else { continue }
        if let (value, range) = findValue(label, line, lines, isName) {
            let found = plain(String(value.text[range]))
            if found.count >= 3 { names.insert(found) }
        }
    }
}

print("쪽\t회전\t서류\t글자줄\t이름\t환자번호\t주민번호\t주소\t전화·카드\t코드\t의료인\t값못찾음\t이름칸\t번호칸")
for (file, image, lines, codes, degrees) in pages {
    var masks: [CGRect] = []
    var count = ["name": 0, "patient": 0, "resident": 0, "address": 0, "contact": 0, "staff": 0, "missing": 0]
    var nameLabelHits = 0, numberLabelHits = 0
    func add(_ key: String, _ rect: CGRect) {
        if basicOnly && !["name", "patient", "resident"].contains(key) { return }
        masks.append(rect)
        count[key]! += 1
    }

    for line in lines {
        let p = line.plain
        if let label = residentLabels.first(where: p.contains) {
            if let (v, r) = findValue(label, line, lines, hasDigit) { add("resident", box(v, r)) } else { count["missing"]! += 1 }
        } else if let label = patientNoLabels.first(where: p.contains), !patientNoExcluded.contains(where: p.contains) {
            numberLabelHits += 1
            if let (v, r) = findValue(label, line, lines, isPatientNo) { add("patient", box(v, r)) } else { count["missing"]! += 1 }
        }
        if let label = contactLabels.first(where: p.contains) {
            if let (v, r) = findValue(label, line, lines, hasDigit) { add("contact", box(v, r)) }
        }
        if p.contains("주소"), !addressExcluded.contains(where: p.contains) {
            if let (v, r) = findValue("주소", line, lines, { !isLabelLike($0) && $0.range(of: "[가-힣]", options: .regularExpression) != nil }) { add("address", box(v, r)) } else { count["missing"]! += 1 }
        }
        if let label = nameLabels.first(where: p.contains) {
            if !staffWords.contains(where: p.contains) { nameLabelHits += 1 }
            if staffWords.contains(where: p.contains) {
                if let (v, r) = findValue(label, line, lines, isName) { add("staff", box(v, r)) }
            } else if let (v, r) = findValue(label, line, lines, isName) {
                add("name", nameMask(v, r))
            } else {
                count["missing"]! += 1
            }
        }
        for (key, pattern) in patterns {
            let regex = try! NSRegularExpression(pattern: pattern)
            for match in regex.matches(in: line.text, range: NSRange(line.text.startIndex..., in: line.text)) {
                if let r = Range(match.range, in: line.text) { add(key == "resident" ? "resident" : "contact", box(line, r)) }
            }
        }
        for number in patientNumbers {
            if let start = offset(of: number, in: p), let r = originalRange(line.text, from: start, count: number.count) {
                add("patient", box(line, r))
            }
        }
        for name in names {
            if let start = offset(of: name, in: p), let r = originalRange(line.text, from: start, count: name.count) {
                add("name", nameMask(line, r))
            }
        }
    }
    if !basicOnly { for code in codes { masks.append(code) } }

    let target = outputDir.appendingPathComponent(file.lastPathComponent)
    // 글자를 못 읽은 쪽은 칠할 곳도 모르므로 칠한 폴더에 남기지 않는다.
    if lines.isEmpty {
        try? FileManager.default.removeItem(at: target)
        print([file.deletingPathExtension().lastPathComponent, "-", "못읽음", "0"].joined(separator: "\t"))
        continue
    }

    let w = image.width, h = image.height
    let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
    ctx.setFillColor(CGColor(red: 0, green: 0, blue: 0, alpha: 1))
    for m in masks {
        ctx.fill(CGRect(x: m.minX * CGFloat(w), y: m.minY * CGFloat(h), width: m.width * CGFloat(w), height: m.height * CGFloat(h)).insetBy(dx: -3, dy: -3))
    }
    // 원본의 메타데이터를 넘기지 않고 픽셀만 새 파일로 저장한다.
    let dest = CGImageDestinationCreateWithURL(target as CFURL, "public.png" as CFString, 1, nil)!
    CGImageDestinationAddImage(dest, ctx.makeImage()!, nil)
    CGImageDestinationFinalize(dest)

    print([file.deletingPathExtension().lastPathComponent, String(degrees), documentKind(lines), String(lines.count), String(count["name"]!), String(count["patient"]!), String(count["resident"]!), String(count["address"]!), String(count["contact"]!), String(codes.count), String(count["staff"]!), String(count["missing"]!), String(nameLabelHits), String(numberLabelHits)].joined(separator: "\t"))
}
print("찾은 환자 이름 종류 수:", names.count, "환자번호 종류 수:", patientNumbers.count)
