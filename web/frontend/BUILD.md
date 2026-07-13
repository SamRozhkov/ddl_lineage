# Frontend Build & Deployment Guide

## Development & Production

The frontend is a Create React App application with `react-app-rewired` and Gravity UI.

```bash
cd web/frontend
npm install
npm start
```

Development:
- `npm start` starts the React dev server on `http://localhost:3000`
- API calls to `/api/*` are proxied to `http://127.0.0.1:5001`

Production build:

```bash
npm run build
```

The Flask backend serves `web/frontend/build/index.html` when that build exists.

## File Structure

```
web/frontend/
├── package.json                # Dependencies + build scripts
├── public/
│   └── index.html
└── src/
    ├── App.tsx
    ├── App.css
    └── index.tsx
```

## Deployment Checklist

- [ ] Install dependencies: `npm install`
- [ ] Build application: `npm run build`
- [ ] Verify `build/index.html` was generated
- [ ] Start frontend: `npm start`
- [ ] Start backend: `python3 web/backend/app.py`
- [ ] Verify running on `http://localhost:3000`
- [ ] Check browser console for any errors

## References

- [Create React App](https://create-react-app.dev/)
- [Gravity UI](https://gravity-ui.com/)
