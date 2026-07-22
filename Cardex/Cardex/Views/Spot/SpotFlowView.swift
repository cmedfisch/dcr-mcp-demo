import SwiftUI
import SwiftData

enum SpotFlowState {
    case camera
    case review(UIImage)
    case tagging(UIImage)
    case confirm(UIImage, Car)
    case done(SpotReward)
}

struct SpotFlowView: View {
    @Environment(\.modelContext) private var modelContext
    @Query(filter: #Predicate<Player> { $0.id == "player" }) private var players: [Player]
    @State private var flowState: SpotFlowState = .camera

    private var player: Player? { players.first }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.cxBackground.ignoresSafeArea()
                content
            }
            .navigationTitle("Spot")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    @ViewBuilder
    private var content: some View {
        switch flowState {
        case .camera:
            CameraView { image in
                flowState = .review(image)
            }
        case .review(let image):
            PhotoReviewView(image: image) {
                flowState = .tagging(image)
            } onRetake: {
                flowState = .camera
            }
        case .tagging(let image):
            CarPickerView { car in
                flowState = .confirm(image, car)
            } onCancel: {
                flowState = .camera
            }
        case .confirm(let image, let car):
            SpotConfirmView(image: image, car: car) { reward in
                flowState = .done(reward)
            } onCancel: {
                flowState = .camera
            }
        case .done(let reward):
            SpotDoneView(reward: reward) {
                flowState = .camera
            }
        }
    }
}

struct SpotDoneView: View {
    let reward: SpotReward
    let onDismiss: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 80))
                .foregroundColor(.cxUncommon)

            Text("Caught!")
                .font(.largeTitle.weight(.bold))
                .foregroundColor(.cxTextPrimary)

            GlassCard {
                VStack(spacing: 8) {
                    Text("+\(reward.xpGained) XP")
                        .font(.title2.weight(.bold))
                        .foregroundColor(.cxAccent)
                    if reward.leveledUp {
                        Text("Level Up! You're now a \(XPEngine.title(for: reward.newLevel))")
                            .font(.subheadline)
                            .foregroundColor(.cxLegendary)
                    }
                }
            }

            Button(action: onDismiss) {
                Text("Spot Another")
                    .font(.headline)
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(
                        RoundedRectangle(cornerRadius: 14)
                            .fill(Color.cxAccent)
                    )
            }
            .padding(.horizontal, 40)
        }
    }
}
