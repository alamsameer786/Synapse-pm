import UIKit
import Capacitor
import UserNotifications
import WebKit

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {
    
    var window: UIWindow?
    var bridge: CAPBridge?
    
    func application(_ application: UIApplication, 
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        
        // Setup window
        window = UIWindow(frame: UIScreen.main.bounds)
        
        // Setup Capacitor bridge
        let bridge = CAPBridge(webView: WKWebView())
        self.bridge = bridge
        
        // Setup view controller
        let viewController = CAPBridgeViewController()
        viewController.bridge = bridge
        window?.rootViewController = viewController
        window?.makeKeyAndVisible()
        
        // Request notification permission
        requestNotificationPermissions()
        
        // Setup push notifications
        UIApplication.shared.registerForRemoteNotifications()
        
        // Set status bar style
        UINavigationBar.appearance().barStyle = .black
        UINavigationBar.appearance().tintColor = UIColor(red: 0/255, green: 180/255, blue: 170/255, alpha: 1.0)
        
        return true
    }
    
    func requestNotificationPermissions() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { granted, error in
            DispatchQueue.main.async {
                if granted {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            }
        }
    }
    
    func application(_ application: UIApplication, 
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        // Send device token to server
        let tokenParts = deviceToken.map { data -> String in
            return String(format: "%02.2hhx", data)
        }
        let token = tokenParts.joined()
        print("📱 Device Token: \(token)")
        
        // Send to server
        NotificationCenter.default.post(name: .capacitorDidRegisterForRemoteNotifications, 
                                        object: token)
    }
    
    func application(_ application: UIApplication, 
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("❌ Failed to register for notifications: \(error)")
    }
    
    func application(_ application: UIApplication, 
                     didReceiveRemoteNotification userInfo: [AnyHashable : Any],
                     fetchCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void) {
        // Handle push notification
        NotificationCenter.default.post(name: .capacitorDidReceiveRemoteNotification, 
                                        object: userInfo)
        completionHandler(.newData)
    }
    
    func application(_ app: UIApplication, open url: URL, 
                     options: [UIApplication.OpenURLOptionsKey : Any] = [:]) -> Bool {
        // Handle deep links
        if url.scheme == "synapsepm" {
            // Process deep link
            handleDeepLink(url)
            return true
        }
        return false
    }
    
    func handleDeepLink(_ url: URL) {
        let path = url.absoluteString.replacingOccurrences(of: "synapsepm://", with: "")
        print("🔗 Deep link: \(path)")
        
        // Send to web view
        if let bridge = bridge {
            let js = "window.handleDeepLink('\(path)');"
            bridge.webView?.evaluateJavaScript(js, completionHandler: nil)
        }
    }
    
    func applicationWillResignActive(_ application: UIApplication) {
        // Sent when the application is about to move from active to inactive state.
    }
    
    func applicationDidEnterBackground(_ application: UIApplication) {
        // Use this method to release shared resources, save user data, and invalidate timers.
    }
    
    func applicationWillEnterForeground(_ application: UIApplication) {
        // Called as part of the transition from the background to the active state.
    }
    
    func applicationDidBecomeActive(_ application: UIApplication) {
        // Restart any tasks that were paused (or not yet started) while the application was inactive.
    }
    
    func applicationWillTerminate(_ application: UIApplication) {
        // Called when the application is about to terminate.
    }
}

// MARK: - Capacitor Notification Extensions
extension Notification.Name {
    static let capacitorDidRegisterForRemoteNotifications = Notification.Name("capacitorDidRegisterForRemoteNotifications")
    static let capacitorDidReceiveRemoteNotification = Notification.Name("capacitorDidReceiveRemoteNotification")
}