import SwiftUI
import SwiftData

struct SpotConfirmView: View {
    let image: UIImage
    let car: Car
    let onConfirm: (SpotReward) -> Void
    let onCancel: () -> Void

    @Environment(\.modelContext) private var modelContext
    @Query(filter: #Predicate<Player> { $0.id == "player" }) private var players: [Player]
    @State private var notes = ""
    @State private var locationName = ""

    private var player: Player? { players.first }

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .frame(maxHeight: 250)
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                GlassCard {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(car.make)
                            .font(.subheadline)
                            .foregroundColor(.cxTextSecondary)
                        Text(car.model)
                            .font(.title2.weight(.bold))
                            .foregroundColor(.cxTextPrimary)
                        HStack {
                            Text(car.displayYear)
                                .font(.subheadline)
                                .foregroundColor(.cxTextSecondary)
                            Spacer()
                            RarityBadge(tier: car.rarity)
                        }
                    }
                }

                GlassCard {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Details")
                            .font(.headline)
                            .foregroundColor(.cxTextPrimary)

                        TextField("Location (optional)", text: $locationName)
                            .foregroundColor(.cxTextPrimary)
                            .padding(10)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(Color.cxSurfaceLight)
                            )

                        TextField("Notes (optional)", text: $notes, axis: .vertical)
                            .foregroundColor(.cxTextPrimary)
                            .lineLimit(3...6)
                            .padding(10)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(Color.cxSurfaceLight)
                            )
                    }
                }

                HStack {
                    Text("+\(car.xpValue) XP")
                        .font(.headline.weight(.bold))
                        .foregroundColor(.cxAccent)
                }

                Button(action: catchCar) {
                    Text("Catch!")
                        .font(.title3.weight(.bold))
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(
                            RoundedRectangle(cornerRadius: 14)
                                .fill(Color.cxAccent)
                        )
                }

                Button("Cancel", action: onCancel)
                    .foregroundColor(.cxTextSecondary)
            }
            .padding()
        }
    }

    private func catchCar() {
        guard let player = player else { return }

        let resized = image.resized(toMaxDimension: 1200)
        guard let fileName = PhotoStorageService.save(image: resized) else { return }

        let spot = Spot(
            car: car,
            photoFileName: fileName,
            locationName: locationName,
            notes: notes
        )
        modelContext.insert(spot)

        let reward = XPEngine.awardSpot(player: player, car: car)
        try? modelContext.save()

        HapticManager.catchCar()
        onConfirm(reward)
    }
}
