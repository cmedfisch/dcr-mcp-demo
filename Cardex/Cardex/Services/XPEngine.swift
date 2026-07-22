import Foundation

enum XPEngine {
    static let levels: [(threshold: Int, title: String)] = [
        (0, "Spotter"),
        (100, "Enthusiast"),
        (300, "Collector"),
        (600, "Connoisseur"),
        (1000, "Expert"),
        (1500, "Aficionado"),
        (2500, "Master"),
        (4000, "Grand Master"),
        (6000, "Champion"),
        (10000, "Legend"),
    ]

    static func level(for xp: Int) -> Int {
        let index = levels.lastIndex(where: { xp >= $0.threshold }) ?? 0
        return index + 1
    }

    static func title(for level: Int) -> String {
        guard level >= 1, level <= levels.count else { return "Legend" }
        return levels[level - 1].title
    }

    static func xpRequired(for level: Int) -> Int {
        guard level >= 1, level <= levels.count else {
            return levels.last?.threshold ?? 10000
        }
        return levels[level - 1].threshold
    }

    static func awardSpot(player: Player, car: Car) -> SpotReward {
        let oldLevel = player.level
        let xp = car.xpValue
        player.totalXP += xp

        let calendar = Calendar.current
        let today = calendar.startOfDay(for: .now)

        if let lastDate = player.lastSpotDate {
            let lastDay = calendar.startOfDay(for: lastDate)
            let daysBetween = calendar.dateComponents([.day], from: lastDay, to: today).day ?? 0
            if daysBetween == 1 {
                player.currentStreak += 1
            } else if daysBetween > 1 {
                player.currentStreak = 1
            }
        } else {
            player.currentStreak = 1
        }

        player.lastSpotDate = .now
        player.longestStreak = max(player.longestStreak, player.currentStreak)

        let leveledUp = player.level > oldLevel
        return SpotReward(xpGained: xp, leveledUp: leveledUp, newLevel: player.level)
    }
}

struct SpotReward {
    let xpGained: Int
    let leveledUp: Bool
    let newLevel: Int
}
