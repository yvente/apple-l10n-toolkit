import SwiftUI

struct SampleApp: View {
    let count: Int
    let name: String
    var body: some View {
        VStack {
            Text("Plain")
            Text("\(count) faces")
            let title = "Saved %@".localized(with: name)
            print("LogKey")
        }
    }
}
