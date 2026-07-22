import Foundation
import SwiftData

@Model
final class Player {
    @Attribute(.unique) var id: String = "player"
    var totalXP: Int = 0
    var currentStreak: Int = 0
    var longestStreak: Int = 0
    var lastSpotDate: Date?
    var joinDate: Date = Date()

    @Relationship(deleteRule: .cascade, inverse: \Achievement.player)
    var achievements: [Achievement] = []

    var level: Int {
        XPEngine.level(for: totalXP)
    }

    var levelTitle: String {
        XPEngine.title(for: level)
    }

    var xpForNextLevel: Int {
        XPEngine.xpRequired(for: level + 1)
    }

    var xpInCurrentLevel: Int {
        let currentThreshold = XPEngine.xpRequired(for: level)
        return totalXP - currentThreshold
    }

    var xpNeededForCurrentLevel: Int {
        let currentThreshold = XPEngine.xpRequired(for: level)
        let nextThreshold = XPEngine.xpRequired(for: level + 1)
        return nextThreshold - currentThreshold
    }

    var levelProgress: Double {
        guard xpNeededForCurrentLevel > 0 else { return 1.0 }
        return Double(xpInCurrentLevel) / Double(xpNeededForCurrentLevel)
    }

    init() {}
}
