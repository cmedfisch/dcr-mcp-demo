import SwiftUI
import AVFoundation
import PhotosUI

struct CameraView: View {
    let onCapture: (UIImage) -> Void
    @State private var selectedItem: PhotosPickerItem?
    @State private var showCamera = false

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            Image(systemName: "camera.viewfinder")
                .font(.system(size: 100))
                .foregroundColor(.cxTextSecondary)

            Text("Spot a car")
                .font(.title2.weight(.semibold))
                .foregroundColor(.cxTextPrimary)

            Text("Take a photo or pick one from your library")
                .font(.subheadline)
                .foregroundColor(.cxTextSecondary)
                .multilineTextAlignment(.center)

            VStack(spacing: 16) {
                Button {
                    showCamera = true
                } label: {
                    Label("Take Photo", systemImage: "camera.fill")
                        .font(.headline)
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(
                            RoundedRectangle(cornerRadius: 14)
                                .fill(Color.cxAccent)
                        )
                }

                PhotosPicker(selection: $selectedItem, matching: .images) {
                    Label("Choose from Library", systemImage: "photo.on.rectangle")
                        .font(.headline)
                        .foregroundColor(.cxAccent)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(
                            RoundedRectangle(cornerRadius: 14)
                                .stroke(Color.cxAccent, lineWidth: 1.5)
                        )
                }
            }
            .padding(.horizontal, 40)

            Spacer()
        }
        .fullScreenCover(isPresented: $showCamera) {
            ImagePickerView(onCapture: onCapture)
                .ignoresSafeArea()
        }
        .onChange(of: selectedItem) { _, newItem in
            guard let item = newItem else { return }
            Task {
                if let data = try? await item.loadTransferable(type: Data.self),
                   let image = UIImage(data: data) {
                    onCapture(image)
                }
            }
        }
    }
}

struct ImagePickerView: UIViewControllerRepresentable {
    let onCapture: (UIImage) -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(onCapture: onCapture) }

    class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let onCapture: (UIImage) -> Void
        init(onCapture: @escaping (UIImage) -> Void) { self.onCapture = onCapture }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage {
                onCapture(image)
            }
            picker.dismiss(animated: true)
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            picker.dismiss(animated: true)
        }
    }
}
