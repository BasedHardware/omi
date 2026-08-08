import Foundation

class TemplateProvider: NSObject, LynxTemplateProvider {
  func loadTemplate(withUrl url: String!, onComplete callback: LynxTemplateLoadBlock!) {
    guard let encodeUrl = url.addingPercentEncoding(withAllowedCharacters: .urlFragmentAllowed),
          let nsUrl = URL(string: encodeUrl) else {
      let errorMsg = "Invalid URL: \(String(describing: url))"
      let error = NSError(domain: "com.lynx",
                          code: 400,
                          userInfo: [NSLocalizedDescriptionKey: errorMsg])
      callback(nil, error)
      return
    }

    let task = URLSession.shared.dataTask(with: nsUrl) { data, response, error in
      DispatchQueue.main.async {
        if let error = error {
          callback(data, error)
        } else if data == nil {
          let errorMsg = "data from \(String(describing: url)) is nil!"
          let dataError = NSError(domain: "com.lynx",
                                  code: 200,
                                  userInfo: [NSLocalizedDescriptionKey: errorMsg])
          callback(nil, dataError)
        } else {
          callback(data, nil)
        }
      }
    }
    task.resume()

  }
}
