import Foundation

class TemplateProvider: NSObject, LynxTemplateProvider {
  func loadTemplate(withUrl url: String!, onComplete callback: LynxTemplateLoadBlock!) {
    if !url.hasPrefix("http") {
      guard let resourceUrl = Bundle.main.url(forResource: url, withExtension: nil),
            let data = try? Data(contentsOf: resourceUrl) else {
        let error = NSError(domain: "com.lynx", code: 404,
                            userInfo: [NSLocalizedDescriptionKey: "Missing bundled template: \(url ?? "nil")"])
        callback(nil, error)
        return
      }
      callback(data, nil)
      return
    }

    guard let encodeUrl = url.addingPercentEncoding(withAllowedCharacters: .urlFragmentAllowed),
          let nsUrl = URL(string: encodeUrl) else {
      let errorMsg = "Invalid URL: \(String(describing: url))"
      let error = NSError(domain: "com.lynx", code: 400,
                          userInfo: [NSLocalizedDescriptionKey: errorMsg])
      callback(nil, error)
      return
    }

    let task = URLSession.shared.dataTask(with: nsUrl) { data, _, error in
      DispatchQueue.main.async {
        if let error = error {
          callback(data, error)
        } else if let data = data {
          callback(data, nil)
        } else {
          let dataError = NSError(domain: "com.lynx", code: 200,
                                  userInfo: [NSLocalizedDescriptionKey: "Template data is nil"])
          callback(nil, dataError)
        }
      }
    }
    task.resume()
  }
}
