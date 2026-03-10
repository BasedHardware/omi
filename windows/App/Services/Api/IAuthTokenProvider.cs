using System.Threading;
using System.Threading.Tasks;

namespace Omi.Windows.App.Services.Api;

public interface IAuthTokenProvider
{
    Task<string?> GetIdTokenAsync(CancellationToken ct = default);
}

