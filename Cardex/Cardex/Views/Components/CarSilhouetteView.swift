import SwiftUI

struct CarSilhouetteView: View {
    let bodyType: String
    let rarity: RarityTier

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.cxSurface)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(rarity.color.opacity(0.3), lineWidth: 1)
                )
            VStack(spacing: 6) {
                Image(systemName: iconForBody)
                    .font(.system(size: 32))
                    .foregroundStyle(rarity.color.opacity(0.4))
                Text("???")
                    .font(.caption.weight(.bold))
                    .foregroundColor(.cxTextSecondary)
            }
        }
    }

    private var iconForBody: String {
        let type = bodyType.lowercased()
        if type.contains("truck") || type.contains("pickup") { return "truck.box.fill" }
        if type.contains("suv") || type.contains("crossover") { return "suv.side.fill" }
        if type.contains("van") || type.contains("minivan") { return "van.fill" }
        if type.contains("convertible") || type.contains("roadster") { return "car.top.radiowaves.rear.right.fill" }
        return "car.fill"
    }
}
