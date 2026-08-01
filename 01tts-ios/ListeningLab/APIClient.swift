import Foundation

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case server(Int, String)
    case decoding(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: "The server address is invalid."
        case .invalidResponse: "The server returned an invalid response."
        case let .server(code, message): "Server error \(code): \(message)"
        case let .decoding(message): "Response decoding failed: \(message)"
        }
    }
}

actor APIClient {
    static let shared = APIClient()

    private let primary = URL(string: "https://api.zhchoice.xyz/")!
    private let fallback = URL(string: "http://42.192.62.145:8080/")!
    private let session: URLSession
    private let fallbackCodes = Set([401, 403, 421, 502, 503, 504])

    init(session: URLSession = .shared) {
        self.session = session
    }

    func today() async throws -> DailyPlan {
        try await request("api/v1/daily-plans/today")
    }

    func library() async throws -> [ContentItem] {
        try await request("api/v1/library")
    }

    func topics() async throws -> [TopicRecommendation] {
        try await request("api/v1/topics/recommendations?limit=6")
    }

    func content(_ uuid: String) async throws -> ContentItem {
        try await request("api/v1/content/\(uuid)")
    }

    func dashboard(clientID: String) async throws -> LearningDashboard {
        try await request("api/v1/learning/dashboard/\(clientID)?days=7")
    }

    func progress(clientID: String, contentID: String) async throws -> LearningProgress {
        try await request("api/v1/learning/progress/\(clientID)/\(contentID)")
    }

    func save(progress: LearningProgress) async throws -> LearningProgress {
        try await request("api/v1/learning/progress", method: "PUT", body: progress)
    }

    func createTask(prompt: String, voice: String, difficulty: String) async throws -> TaskItem {
        try await request(
            "api/v1/tasks",
            method: "POST",
            body: CreateTaskRequest(prompt: prompt, voice: voice, difficulty: difficulty)
        )
    }

    func createLesson(topic: String, category: String, voice: String, level: String) async throws -> ContentItem {
        try await request(
            "api/v1/long-lessons",
            method: "POST",
            body: CreateLongLessonRequest(
                topic: topic,
                category: category,
                voice: voice,
                level: level,
                sourceMode: "AUTO"
            )
        )
    }

    func uploadRecording(taskID: String, fileURL: URL) async throws -> AnswerItem {
        let boundary = "ListeningLab-\(UUID().uuidString)"
        var data = Data()
        data.append("--\(boundary)\r\n")
        data.append("Content-Disposition: form-data; name=\"audio\"; filename=\"answer.m4a\"\r\n")
        data.append("Content-Type: audio/mp4\r\n\r\n")
        data.append(try Data(contentsOf: fileURL))
        data.append("\r\n--\(boundary)--\r\n")
        return try await request(
            "api/v1/tasks/\(taskID)/answers",
            method: "POST",
            rawBody: data,
            contentType: "multipart/form-data; boundary=\(boundary)"
        )
    }

    func answer(_ uuid: String) async throws -> AnswerItem {
        try await request("api/v1/answers/\(uuid)")
    }

    nonisolated func mediaURL(_ raw: String?) -> URL? {
        guard let raw, !raw.isEmpty else { return nil }
        if let absolute = URL(string: raw), absolute.scheme != nil { return absolute }
        return URL(string: raw.trimmingCharacters(in: CharacterSet(charactersIn: "/")), relativeTo: fallback)?.absoluteURL
    }

    private func request<Response: Decodable, Body: Encodable>(
        _ path: String,
        method: String = "GET",
        body: Body
    ) async throws -> Response {
        let data = try JSONEncoder().encode(body)
        return try await request(path, method: method, rawBody: data, contentType: "application/json")
    }

    private func request<Response: Decodable>(
        _ path: String,
        method: String = "GET",
        rawBody: Data? = nil,
        contentType: String? = nil
    ) async throws -> Response {
        do {
            return try await perform(base: primary, path: path, method: method, body: rawBody, contentType: contentType)
        } catch let error as APIError {
            if case let .server(code, _) = error, !fallbackCodes.contains(code) { throw error }
            return try await perform(base: fallback, path: path, method: method, body: rawBody, contentType: contentType)
        } catch {
            return try await perform(base: fallback, path: path, method: method, body: rawBody, contentType: contentType)
        }
    }

    private func request<Response: Decodable>(_ path: String) async throws -> Response {
        try await request(path, method: "GET", rawBody: nil, contentType: nil)
    }

    private func perform<Response: Decodable>(
        base: URL,
        path: String,
        method: String,
        body: Data?,
        contentType: String?
    ) async throws -> Response {
        guard let url = URL(string: path, relativeTo: base)?.absoluteURL else { throw APIError.invalidURL }
        var request = URLRequest(url: url, timeoutInterval: 45)
        request.httpMethod = method
        request.httpBody = body
        if let contentType { request.setValue(contentType, forHTTPHeaderField: "Content-Type") }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard 200..<300 ~= http.statusCode else {
            throw APIError.server(http.statusCode, String(data: data, encoding: .utf8) ?? "Unknown response")
        }
        do {
            return try JSONDecoder().decode(Response.self, from: data)
        } catch {
            throw APIError.decoding(error.localizedDescription)
        }
    }
}

private extension Data {
    mutating func append(_ string: String) {
        append(Data(string.utf8))
    }
}
