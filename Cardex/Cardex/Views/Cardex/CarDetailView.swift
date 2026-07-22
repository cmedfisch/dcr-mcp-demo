import SwiftUI

struct CarDetailView: View {
    let car: Car

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                heroSection
                specsSection
                if !car.spots.isEmpty {
                    spotsSection
                }
            }
            .padding()
        }
        .background(Color.cxBackground)
        .navigationTitle(car.model)
        .navigationBarTitleDisplayMode(.inline)
    }

    private var heroSection: some View {
        VStack(spacing: 12) {
            if let spot = car.spots.first,
               let image = PhotoStorageService.loadImage(fileName: spot.photoFileName) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .clipShape(RoundedRectangle(cornerRadius: 16))
            } else {
                CarSilhouetteView(bodyType: car.bodyType, rarity: car.rarity)
                    .frame(height: 200)
            }

            VStack(spacing: 4) {
                Text(car.make)
                    .font(.subheadline)
                    .foregroundColor(.cxTextSecondary)
                Text(car.model)
                    .font(.title.weight(.bold))
                    .foregroundColor(.cxTextPrimary)
                if !car.generation.isEmpty {
                    Text(car.generation)
                        .font(.subheadline)
                        .foregroundColor(.cxTextSecondary)
                }
                Text(car.displayYear)
                    .font(.subheadline)
                    .foregroundColor(.cxTextSecondary)
            }

            RarityBadge(tier: car.rarity)

            if car.isCaught {
                Label("Caught!", systemImage: "checkmark.seal.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundColor(.cxUncommon)
            }
        }
    }

    private var specsSection: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: 12) {
                Text("Specs")
                    .font(.headline)
                    .foregroundColor(.cxTextPrimary)

                if !car.bodyType.isEmpty {
                    specRow(label: "Body", value: car.bodyType)
                }
                if !car.engineType.isEmpty {
                    specRow(label: "Engine", value: car.engineType)
                }
                if !car.displacement.isEmpty {
                    specRow(label: "Displacement", value: car.displacement)
                }
                if let hp = car.horsepower {
                    specRow(label: "Horsepower", value: "\(hp) hp")
                }
                if let production = car.productionCount {
                    specRow(label: "Production", value: production.formatted())
                }
                specRow(label: "XP Value", value: "+\(car.xpValue) XP")
            }
        }
    }

    private func specRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.subheadline)
                .foregroundColor(.cxTextSecondary)
            Spacer()
            Text(value)
                .font(.subheadline.weight(.medium))
                .foregroundColor(.cxTextPrimary)
        }
    }

    private var spotsSection: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: 12) {
                Text("Sightings (\(car.spots.count))")
                    .font(.headline)
                    .foregroundColor(.cxTextPrimary)

                ForEach(car.spots) { spot in
                    HStack {
                        if let thumb = PhotoStorageService.loadThumbnail(fileName: spot.photoFileName) {
                            Image(uiImage: thumb)
                                .resizable()
                                .scaledToFill()
                                .frame(width: 50, height: 50)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                        }
                        VStack(alignment: .leading) {
                            Text(spot.dateCaught.formatted(date: .abbreviated, time: .omitted))
                                .font(.subheadline)
                                .foregroundColor(.cxTextPrimary)
                            if !spot.locationName.isEmpty {
                                Text(spot.locationName)
                                    .font(.caption)
                                    .foregroundColor(.cxTextSecondary)
                            }
                        }
                        Spacer()
                    }
                }
            }
        }
    }
}
