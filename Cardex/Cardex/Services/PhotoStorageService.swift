import UIKit

enum PhotoStorageService {
    private static var photosDirectory: URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let dir = docs.appendingPathComponent("SpotPhotos", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private static var thumbnailsDirectory: URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let dir = docs.appendingPathComponent("SpotThumbnails", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    static func save(image: UIImage) -> String? {
        let fileName = UUID().uuidString + ".jpg"
        guard let data = image.jpegData(compressionQuality: 0.8) else { return nil }

        let fileURL = photosDirectory.appendingPathComponent(fileName)
        do {
            try data.write(to: fileURL)
            saveThumbnail(image: image, fileName: fileName)
            return fileName
        } catch {
            return nil
        }
    }

    private static func saveThumbnail(image: UIImage, fileName: String) {
        let size = CGSize(width: 300, height: 300)
        let renderer = UIGraphicsImageRenderer(size: size)
        let thumb = renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
        guard let data = thumb.jpegData(compressionQuality: 0.6) else { return }
        let url = thumbnailsDirectory.appendingPathComponent(fileName)
        try? data.write(to: url)
    }

    static func loadImage(fileName: String) -> UIImage? {
        let url = photosDirectory.appendingPathComponent(fileName)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return UIImage(data: data)
    }

    static func loadThumbnail(fileName: String) -> UIImage? {
        let url = thumbnailsDirectory.appendingPathComponent(fileName)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return UIImage(data: data)
    }

    static func delete(fileName: String) {
        let photoURL = photosDirectory.appendingPathComponent(fileName)
        let thumbURL = thumbnailsDirectory.appendingPathComponent(fileName)
        try? FileManager.default.removeItem(at: photoURL)
        try? FileManager.default.removeItem(at: thumbURL)
    }
}
