import SwiftUI
import SwiftData

struct CarPickerView: View {
    let onSelect: (Car) -> Void
    let onCancel: () -> Void

    @Query(sort: \Car.make) private var allCars: [Car]
    @State private var searchText = ""
    @State private var selectedMake: String?
    @State private var selectedModel: String?

    private var makes: [String] {
        Array(Set(allCars.map(\.make))).sorted()
    }

    private var modelsForMake: [String] {
        guard let make = selectedMake else { return [] }
        return Array(Set(allCars.filter { $0.make == make }.map(\.model))).sorted()
    }

    private var carsForModel: [Car] {
        guard let make = selectedMake, let model = selectedModel else { return [] }
        return allCars.filter { $0.make == make && $0.model == model }
            .sorted { $0.yearStart > $1.yearStart }
    }

    private var filteredMakes: [String] {
        if searchText.isEmpty { return makes }
        return makes.filter { $0.lowercased().contains(searchText.lowercased()) }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().background(Color.cxSurfaceLight)
            content
        }
    }

    private var header: some View {
        HStack {
            Button("Cancel", action: onCancel)
                .foregroundColor(.cxTextSecondary)
            Spacer()
            Text(headerTitle)
                .font(.headline)
                .foregroundColor(.cxTextPrimary)
            Spacer()
            if selectedMake != nil {
                Button("Back") {
                    if selectedModel != nil {
                        selectedModel = nil
                    } else {
                        selectedMake = nil
                    }
                }
                .foregroundColor(.cxAccent)
            } else {
                Color.clear.frame(width: 50)
            }
        }
        .padding()
    }

    private var headerTitle: String {
        if selectedModel != nil { return "Pick Year/Gen" }
        if selectedMake != nil { return "Pick Model" }
        return "Pick Make"
    }

    @ViewBuilder
    private var content: some View {
        if selectedModel != nil {
            yearList
        } else if selectedMake != nil {
            modelList
        } else {
            makeList
        }
    }

    private var makeList: some View {
        VStack(spacing: 0) {
            SearchBar(text: $searchText, placeholder: "Search makes...")
                .padding()
            List(filteredMakes, id: \.self) { make in
                Button {
                    selectedMake = make
                    searchText = ""
                    HapticManager.tap()
                } label: {
                    HStack {
                        Text(make)
                            .foregroundColor(.cxTextPrimary)
                        Spacer()
                        Text("\(allCars.filter { $0.make == make }.count)")
                            .font(.caption)
                            .foregroundColor(.cxTextSecondary)
                        Image(systemName: "chevron.right")
                            .font(.caption)
                            .foregroundColor(.cxTextSecondary)
                    }
                }
            }
            .listStyle(.plain)
        }
    }

    private var modelList: some View {
        List(modelsForMake, id: \.self) { model in
            Button {
                selectedModel = model
                HapticManager.tap()
            } label: {
                HStack {
                    Text(model)
                        .foregroundColor(.cxTextPrimary)
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.caption)
                        .foregroundColor(.cxTextSecondary)
                }
            }
        }
        .listStyle(.plain)
    }

    private var yearList: some View {
        List(carsForModel) { car in
            Button {
                HapticManager.tap()
                onSelect(car)
            } label: {
                HStack {
                    VStack(alignment: .leading) {
                        Text(car.displayYear)
                            .foregroundColor(.cxTextPrimary)
                        if !car.generation.isEmpty {
                            Text(car.generation)
                                .font(.caption)
                                .foregroundColor(.cxTextSecondary)
                        }
                    }
                    Spacer()
                    RarityBadge(tier: car.rarity)
                }
            }
        }
        .listStyle(.plain)
    }
}
