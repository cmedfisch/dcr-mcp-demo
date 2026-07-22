import SwiftUI

struct AchievementListView: View {
    let player: Player

    private var earnedIDs: Set<String> {
        Set(player.achievements.map(\.definitionID))
    }

    var body: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("Achievements")
                        .font(.headline)
                        .foregroundColor(.cxTextPrimary)
                    Spacer()
                    Text("\(earnedIDs.count)/\(AchievementDefinition.allCases.count)")
                        .font(.caption)
                        .foregroundColor(.cxTextSecondary)
                }

                ForEach(Array(AchievementDefinition.allCases), id: \.rawValue) { def in
                    achievementRow(def: def)
                }
            }
        }
    }

    private func achievementRow(def: AchievementDefinition) -> some View {
        let isEarned = earnedIDs.contains(def.rawValue)
        return HStack(spacing: 12) {
            Image(systemName: def.icon)
                .font(.title3)
                .foregroundColor(isEarned ? .cxAccent : Color.cxTextSecondary.opacity(0.4))
                .frame(width: 30)

            VStack(alignment: .leading) {
                Text(def.title)
                    .font(.subheadline.weight(.medium))
                    .foregroundColor(isEarned ? .cxTextPrimary : .cxTextSecondary)
                Text(def.description)
                    .font(.caption)
                    .foregroundColor(.cxTextSecondary)
            }

            Spacer()

            if isEarned {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.cxUncommon)
            }
        }
        .opacity(isEarned ? 1.0 : 0.5)
    }
}
