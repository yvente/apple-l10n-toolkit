import SwiftUI

struct Sample: View {
    let index: Int
    let count: Int
    let name: String
    var body: some View {
        VStack {
            Text("Face \(index + 1)")
            Text("\(count) items")
            Text("Saved \(name)")
            Label("Choose Sticker", systemImage: "square.grid.2x2")
            Text("Totally Untranslated Title")
            Button("Click Me Now") {}
            Text("Saved %@")
        }
    }
}
