import SwiftUI

struct StatsGridView: View {
    let player: Player
    let totalCars: Int
    let caughtCars: Int

    private let columns = [
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12),
    ]

    var body: some View {
        LazyVGrid(columns: columns, spacing: 12) {
            statCard(title: "Total XP", value: "\(player.totalXP)", icon: "star.fill", color: .cxAccent)
            statCard(title: "Cars Caught", value: "\(caughtCars)/\(totalCars)", icon: "car.fill", color: .cxSecondary)
            statCard(title: "Current Streak", value: "\(player.currentStreak) days", icon: "flame.fill", color: .cxEpic)
            statCard(title: "Longest Streak", value: "\(player.longestStreak) days", icon: "trophy.fill", color: .cxLegendary)
        }
    }

    private func statCard(title: String, value: String, icon: String, color: Color) -> some View {
        GlassCard {
            VStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundStyle(color)
                Text(value)
                    .font(.headline.weight(.bold))
                    .foregroundColor(.cxTextPrimary)
                Text(title)
                    .font(.caption)
                    .foregroundColor(.cxTextSecondary)
            }
            .frame(maxWidth: .infinity)
        }
    }
}
