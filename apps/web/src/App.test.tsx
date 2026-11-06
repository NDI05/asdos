import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import App from './App';

describe('login screen', () => {
  it('renders the Indonesian sign-in form without a default password', () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain('Masuk untuk mulai mengoreksi.');
    expect(html).toContain('Nama pengguna');
    expect(html).toContain('Kata sandi');
    expect(html).toContain('autoComplete="username"');
    expect(html).toContain('autoComplete="current-password"');
    expect(html).toContain('type="password"');
    expect(html).not.toMatch(/type="password"[^>]*value="[^"]+"/);
  });
});
