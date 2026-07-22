import SwiftUI

struct RarityBadge: View {
    let tier: RarityTier

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: tier.icon)
                .font(.caption2)
            Text(tier.name)
                .font(.caption.weight(.semibold))
        }
        .foregroundStyle(tier.color)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            Capsule()
                .fill(tier.color.opacity(0.15))
        )
    }
}
