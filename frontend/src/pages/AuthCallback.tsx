import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

/** Read `#token=...` from the URL fragment and strip it from the address bar / history. */
function consumeTokenFromHash(): string | null {
  const hash = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash;
  const token = new URLSearchParams(hash).get('token');
  if (token) {
    // Remove the fragment so the token is not left in the address bar or browser history.
    window.history.replaceState(null, '', window.location.pathname + window.location.search);
  }
  return token;
}

const AuthCallback: React.FC = () => {
  const { setToken } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    // The backend delivers the token in the URL fragment (#token=), which browsers never send
    // to the server (no access-log / Referer leak). Read and clear it immediately.
    const token = consumeTokenFromHash();

    if (token) {
      // Store token and update auth state
      setToken(token);

      // Redirect to home
      navigate('/', { replace: true });
    } else {
      // No token, redirect to login with error
      navigate('/login?error=no_token', { replace: true });
    }
  }, [setToken, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
        <p className="mt-4 text-gray-400">Completing authentication...</p>
      </div>
    </div>
  );
};

export default AuthCallback;
