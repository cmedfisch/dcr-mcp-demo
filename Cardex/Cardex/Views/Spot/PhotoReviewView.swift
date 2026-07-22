import SwiftUI

struct PhotoReviewView: View {
    let image: UIImage
    let onAccept: () -> Void
    let onRetake: () -> Void

    var body: some View {
        VStack(spacing: 20) {
            Image(uiImage: image)
                .resizable()
                .scaledToFit()
                .clipShape(RoundedRectangle(cornerRadius: 16))
                .padding()

            HStack(spacing: 20) {
                Button(action: onRetake) {
                    Label("Retake", systemImage: "arrow.counterclockwise")
                        .font(.headline)
                        .foregroundColor(.cxTextSecondary)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(
                            RoundedRectangle(cornerRadius: 14)
                                .fill(Color.cxSurface)
                        )
                }

                Button(action: onAccept) {
                    Label("Use Photo", systemImage: "checkmark")
                        .font(.headline)
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(
                            RoundedRectangle(cornerRadius: 14)
                                .fill(Color.cxAccent)
                        )
                }
            }
            .padding(.horizontal)
        }
    }
}
