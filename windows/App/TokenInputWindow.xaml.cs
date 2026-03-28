using System.Windows;
using Omi.Windows.App.Services.Auth;

namespace Omi.Windows.App;

public partial class TokenInputWindow : Window
{
    private readonly AuthService _authService;

    public TokenInputWindow(AuthService authService)
    {
        _authService = authService;
        InitializeComponent();
    }

    private async void OnValidateClick(object sender, RoutedEventArgs e)
    {
        var code = TokenTextBox.Text;
        // Pour l’instant on suppose que le redirect_uri utilisé pour /v1/auth/authorize est omi://auth/callback
        var ok = await _authService.SignInWithAuthCodeAsync(code, null);
        if (!ok)
        {
            MessageBox.Show(this, "Impossible d’échanger le code contre un jeton Omi.\nVérifie que tu utilises le même redirect_uri et que le code n’a pas expiré.", "Erreur", MessageBoxButton.OK,
                MessageBoxImage.Error);
            return;
        }

        DialogResult = true;
        Close();
    }

    private void OnOpenAuthPageClick(object sender, RoutedEventArgs e)
    {
        // Ouvre le flux d’authentification standard sur le backend existant
        _authService.OpenAuthPage("apple", null);
    }
}

