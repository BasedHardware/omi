using System.Windows;

namespace Omi.Windows.App.Services.Notifications;

public class WindowsNotificationService
{
    public void ShowInfo(string title, string message)
    {
        // Phase 2 : fallback simple en attendant une intégration Toast complète
        MessageBox.Show(message, title, MessageBoxButton.OK, MessageBoxImage.Information);
    }
}

