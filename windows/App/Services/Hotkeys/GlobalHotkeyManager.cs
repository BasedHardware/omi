using System;
using System.Runtime.InteropServices;
using System.Windows.Interop;

namespace Omi.Windows.App.Services.Hotkeys;

public sealed class GlobalHotkeyManager : IDisposable
{
    private const int HotkeyId = 1;
    private const int WmHotkey = 0x0312;

    [DllImport("user32.dll")]
    private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [DllImport("user32.dll")]
    private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    private readonly Action _onToggleFloatingBar;
    private HwndSource? _source;

    public GlobalHotkeyManager(Action onToggleFloatingBar)
    {
        _onToggleFloatingBar = onToggleFloatingBar;
    }

    public void Register(HwndSource source)
    {
        _source = source;
        _source.AddHook(WndProc);

        const uint modifiers = 0x0002 | 0x0004; // CTRL + ALT
        const uint vkO = 0x4F; // O

        RegisterHotKey(_source.Handle, HotkeyId, modifiers, vkO);
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg == WmHotkey && wParam.ToInt32() == HotkeyId)
        {
            _onToggleFloatingBar();
            handled = true;
        }

        return IntPtr.Zero;
    }

    public void Dispose()
    {
        if (_source != null)
        {
            UnregisterHotKey(_source.Handle, HotkeyId);
            _source.RemoveHook(WndProc);
            _source = null;
        }
    }
}

