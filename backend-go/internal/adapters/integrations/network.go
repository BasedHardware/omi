package integrations

import (
	"context"
	"errors"
	"net"
	"net/netip"
)

var errUnsafeAddress = errors.New("integration: destination address is not public")

func publicDial(resolver *net.Resolver, dialer *net.Dialer) func(context.Context, string, string) (net.Conn, error) {
	return func(ctx context.Context, network, address string) (net.Conn, error) {
		host, port, err := net.SplitHostPort(address)
		if err != nil {
			return nil, errUnsafeAddress
		}
		ips, err := resolver.LookupNetIP(ctx, "ip", host)
		if err != nil {
			return nil, err
		}
		if err := validateAddresses(ips); err != nil {
			return nil, err
		}
		var dialErr error
		for _, ip := range ips {
			conn, err := dialer.DialContext(ctx, network, net.JoinHostPort(ip.String(), port))
			if err == nil {
				return conn, nil
			}
			dialErr = err
		}
		return nil, dialErr
	}
}

func validateAddresses(ips []netip.Addr) error {
	if len(ips) == 0 {
		return errUnsafeAddress
	}
	for _, ip := range ips {
		if !publicAddress(ip.Unmap()) {
			return errUnsafeAddress
		}
	}
	return nil
}

func publicAddress(ip netip.Addr) bool {
	if !ip.IsGlobalUnicast() || ip.IsPrivate() || ip.Zone() != "" {
		return false
	}
	if ip.Is6() && !netip.MustParsePrefix("2000::/3").Contains(ip) {
		return false
	}
	for _, block := range [...]string{
		"0.0.0.0/8", "100.64.0.0/10", "192.0.0.0/24", "192.0.2.0/24",
		"192.88.99.0/24", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "240.0.0.0/4",
		"2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20",
	} {
		if netip.MustParsePrefix(block).Contains(ip) {
			return false
		}
	}
	return true
}
