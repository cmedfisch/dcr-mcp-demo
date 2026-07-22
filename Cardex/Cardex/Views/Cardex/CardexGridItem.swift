import SwiftUI

struct CardexGridItem: View {
    let car: Car

    var body: some View {
        if car.isCaught {
            caughtView
        } else {
            CarSilhouetteView(bodyType: car.bodyType, rarity: car.rarity)
                .aspectRatio(1, contentMode: .fit)
        }
    }

    private var caughtView: some View {
        ZStack(alignment: .bottomLeading) {
            if let spot = car.spots.first,
               let thumb = PhotoStorageService.loadThumbnail(fileName: spot.photoFileName) {
                Image(uiImage: thumb)
                    .resizable()
                    .scaledToFill()
                    .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity)
                    .aspectRatio(1, contentMode: .fill)
                    .clipped()
            } else {
                Rectangle()
                    .fill(Color.cxSurface)
                    .overlay(
                        Image(systemName: "car.fill")
                            .font(.title2)
                            .foregroundStyle(car.rarity.color)
                    )
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(car.model)
                    .font(.caption2.weight(.bold))
                    .foregroundColor(.white)
                    .lineLimit(1)
            }
            .padding(6)
            .background(
                LinearGradient(colors: [.black.opacity(0.7), .clear], startPoint: .bottom, endPoint: .top)
            )
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(car.rarity.color.opacity(0.5), lineWidth: 1.5)
        )
        .aspectRatio(1, contentMode: .fit)
    }
}
