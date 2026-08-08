import Foundation

class GenericResourceFetcher: NSObject, LynxGenericResourceFetcher {

  func fetchResource(_ request: LynxResourceRequest, onComplete callback: @escaping LynxGenericResourceCompletionBlock) -> () -> Void {
    guard let url = URL(string: request.url) else {
      let error = NSError(domain: NSCocoaErrorDomain,
                          code: NSURLErrorBadURL,
                          userInfo: [NSLocalizedDescriptionKey: "Invalid URL: \(request.url)"])
      callback(nil, error)
      return {}
    }

    let urlRequest = URLRequest(url: url,
                                cachePolicy: .reloadIgnoringCacheData,
                                timeoutInterval: 5)

    let dataTask = URLSession.shared.dataTask(with: urlRequest) { data, response, error in
      callback(data, error)
    }

    dataTask.resume()
    return {}
  }

  func fetchResourcePath(_ request: LynxResourceRequest, onComplete callback: @escaping LynxGenericResourcePathCompletionBlock) -> () -> Void {
    let error = NSError(domain: NSCocoaErrorDomain,
                        code: 100,
                        userInfo: [NSLocalizedDescriptionKey: "fetchResourcePath not implemented yet."])
    callback(nil, error)
    return {}
  }

  func fetchStream(_ request: LynxResourceRequest, withStream delegate: LynxResourceStreamLoadDelegate) -> () -> Void {
    delegate.onError("fetchStream not implemented yet.")
    return {}
  }
}
