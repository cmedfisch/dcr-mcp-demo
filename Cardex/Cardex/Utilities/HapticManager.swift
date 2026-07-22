import UIKit

enum HapticManager {
    static func impact(_ style: UIImpactFeedbackGenerator.FeedbackStyle = .medium) {
        UIImpactFeedbackGenerator(style: style).impactOccurred()
    }

    static func notification(_ type: UINotificationFeedbackGenerator.FeedbackType) {
        UINotificationFeedbackGenerator().notificationOccurred(type)
    }

    static func catchCar() {
        impact(.heavy)
    }

    static func levelUp() {
        notification(.success)
    }

    static func achievement() {
        notification(.success)
    }

    static func tap() {
        impact(.light)
    }
}
