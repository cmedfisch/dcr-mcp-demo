import UIKit

extension UIImage {
    func resized(toMaxDimension maxDim: CGFloat) -> UIImage {
        let ratio = min(maxDim / size.width, maxDim / size.height)
        guard ratio < 1.0 else { return self }
        let newSize = CGSize(width: size.width * ratio, height: size.height * ratio)
        let renderer = UIGraphicsImageRenderer(size: newSize)
        return renderer.image { _ in
            draw(in: CGRect(origin: .zero, size: newSize))
        }
    }
}
