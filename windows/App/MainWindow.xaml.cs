using System;
using System.Windows;
using System.Windows.Interop;
using Omi.Windows.App.Services.Audio;
using Omi.Windows.App.Services.Auth;
using Omi.Windows.App.Services.Hotkeys;
using Omi.Windows.App.Services.Notifications;
using Omi.Windows.App.Services.Transcription;
using Omi.Windows.App.ViewModels;
using Omi.Windows.App.FloatingBar;

namespace Omi.Windows.App;

public partial class MainWindow : Window
{
    private readonly CaptureViewModel _captureViewModel;
    private readonly GlobalHotkeyManager _hotkeyManager;
    private readonly WindowsNotificationService _notificationService = new();
    private FloatingBarWindow? _floatingBar;

    public MainWindow()
    {
        InitializeComponent();

        // Wiring minimal manuel pour la phase 1
        var authService = new AuthService(new System.Net.Http.HttpClient());
        var sttClient = new SttWebSocketClient(authService);
        var audioService = new AudioCaptureService();
        _captureViewModel = new CaptureViewModel(audioService, sttClient);

        DataContext = _captureViewModel;

        if (!authService.IsAuthenticated)
        {
            var tokenWindow = new TokenInputWindow(authService);
            tokenWindow.ShowDialog();
        }

        Loaded += OnLoaded;
        Closed += OnClosed;

        _hotkeyManager = new GlobalHotkeyManager(ToggleFloatingBar);
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        var source = (HwndSource)PresentationSource.FromVisual(this)!;
        _hotkeyManager.Register(source);

        _notificationService.ShowInfo("Omi pour Windows", "App démarrée. Raccourci barre flottante : Ctrl+Alt+O.");
    }

    private void OnClosed(object? sender, EventArgs e)
    {
        _hotkeyManager.Dispose();
        _floatingBar?.Close();
    }

    private void ToggleFloatingBar()
    {
        if (_floatingBar is { IsVisible: true })
        {
            _floatingBar.Hide();
            return;
        }

        if (_floatingBar is null)
        {
            _floatingBar = new FloatingBarWindow
            {
                Left = SystemParameters.WorkArea.Right - 420,
                Top = SystemParameters.WorkArea.Bottom - 120
            };
        }

        _floatingBar.Show();
        _floatingBar.Activate();
    }

    private async void OnStartRecordingClick(object sender, RoutedEventArgs e)
    {
        await _captureViewModel.StartAsync();
    }

    private async void OnStopRecordingClick(object sender, RoutedEventArgs e)
    {
        await _captureViewModel.StopAsync();
    }
}