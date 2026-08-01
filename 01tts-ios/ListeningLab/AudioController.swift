import AVFoundation
import Combine
import Foundation

@MainActor
final class AudioController: ObservableObject {
    @Published var isPlaying = false
    @Published var positionMs = 0
    @Published var durationMs = 0
    @Published var rate: Float = 1
    @Published var errorMessage: String?

    private var player: AVPlayer?
    private var observer: Any?

    func load(_ url: URL) {
        if let observer, let player { player.removeTimeObserver(observer) }
        let item = AVPlayerItem(url: url)
        player = AVPlayer(playerItem: item)
        positionMs = 0
        durationMs = 0
        observer = player?.addPeriodicTimeObserver(
            forInterval: CMTime(seconds: 0.2, preferredTimescale: 600),
            queue: .main
        ) { [weak self] time in
            Task { @MainActor in
                guard let self else { return }
                self.positionMs = max(0, Int(time.seconds * 1_000))
                if let seconds = self.player?.currentItem?.duration.seconds, seconds.isFinite {
                    self.durationMs = Int(seconds * 1_000)
                }
                self.isPlaying = self.player?.timeControlStatus == .playing
            }
        }
        do {
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio)
            try AVAudioSession.sharedInstance().setActive(true)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func toggle() {
        guard let player else { return }
        if player.timeControlStatus == .playing {
            player.pause()
        } else {
            player.playImmediately(atRate: rate)
        }
        isPlaying = player.timeControlStatus == .playing
    }

    func seek(to milliseconds: Int) {
        player?.seek(to: CMTime(seconds: Double(max(0, milliseconds)) / 1_000, preferredTimescale: 600))
    }

    func skip(_ seconds: Double) {
        seek(to: positionMs + Int(seconds * 1_000))
    }

    func setRate(_ value: Float) {
        rate = value
        if isPlaying { player?.rate = value }
    }
}

@MainActor
final class RecorderController: NSObject, ObservableObject, AVAudioRecorderDelegate {
    @Published var isRecording = false
    @Published var elapsed = 0
    @Published var errorMessage: String?

    private var recorder: AVAudioRecorder?
    private var timer: Timer?
    private(set) var recordingURL: URL?

    func start() async {
        let granted = await AVAudioApplication.requestRecordPermission()
        guard granted else {
            errorMessage = "Microphone permission is required."
            return
        }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .spokenAudio, options: [.defaultToSpeaker])
            try session.setActive(true)
            let url = FileManager.default.temporaryDirectory.appendingPathComponent("answer-\(UUID().uuidString).m4a")
            recorder = try AVAudioRecorder(
                url: url,
                settings: [
                    AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                    AVSampleRateKey: 44_100,
                    AVNumberOfChannelsKey: 1,
                    AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
                ]
            )
            recorder?.delegate = self
            recorder?.record()
            recordingURL = url
            elapsed = 0
            isRecording = true
            timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
                Task { @MainActor in self?.elapsed += 1 }
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func stop() -> URL? {
        recorder?.stop()
        timer?.invalidate()
        timer = nil
        isRecording = false
        return recordingURL
    }
}
