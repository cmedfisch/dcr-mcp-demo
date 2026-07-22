import SwiftUI
import SwiftData

struct ProfileView: View {
    @Query(filter: #Predicate<Player> { $0.id == "player" }) private var players: [Player]
    @Query private var allCars: [Car]
    @Query private var allSpots: [Spot]

    private var player: Player? { players.first }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    if let player = player {
                        levelSection(player: player)
                        StatsGridView(player: player, totalCars: allCars.count, caughtCars: caughtCount)
                        AchievementListView(player: player)
                        recentSpotsSection
                    }
                }
                .padding()
            }
            .background(Color.cxBackground)
            .navigationTitle("Profile")
        }
    }

    private var caughtCount: Int {
        allCars.filter(\.isCaught).count
    }

    private func levelSection(player: Player) -> some View {
        GlassCard {
            VStack(spacing: 12) {
                Image(systemName: "person.circle.fill")
                    .font(.system(size: 60))
                    .foregroundColor(.cxAccent)

                Text(player.levelTitle)
                    .font(.title2.weight(.bold))
                    .foregroundColor(.cxTextPrimary)

                Text("Level \(player.level)")
                    .font(.subheadline)
                    .foregroundColor(.cxTextSecondary)

                LevelProgressBar(progress: player.levelProgress)

                Text("\(player.xpInCurrentLevel) / \(player.xpNeededForCurrentLevel) XP")
                    .font(.caption)
                    .foregroundColor(.cxTextSecondary)
            }
        }
    }

    private var recentSpotsSection: some View {
        let recentSpots = allSpots.sorted { $0.dateCaught > $1.dateCaught }.prefix(5)
        return GlassCard {
            VStack(alignment: .leading, spacing: 12) {
                Text("Recent Spots")
                    .font(.headline)
                    .foregroundColor(.cxTextPrimary)

                if recentSpots.isEmpty {
                    Text("No spots yet. Go catch some cars!")
                        .font(.subheadline)
                        .foregroundColor(.cxTextSecondary)
                } else {
                    ForEach(Array(recentSpots)) { spot in
                        HStack(spacing: 10) {
                            if let thumb = PhotoStorageService.loadThumbnail(fileName: spot.photoFileName) {
                                Image(uiImage: thumb)
                                    .resizable()
                                    .scaledToFill()
                                    .frame(width: 44, height: 44)
                                    .clipShape(RoundedRectangle(cornerRadius: 8))
                            }
                            VStack(alignment: .leading) {
                                Text(spot.car?.model ?? "Unknown")
                                    .font(.subheadline.weight(.medium))
                                    .foregroundColor(.cxTextPrimary)
                                Text(spot.dateCaught.formatted(date: .abbreviated, time: .omitted))
                                    .font(.caption)
                                    .foregroundColor(.cxTextSecondary)
                            }
                            Spacer()
                            if let car = spot.car {
                                RarityBadge(tier: car.rarity)
                            }
                        }
                    }
                }
            }
        }
    }
}
