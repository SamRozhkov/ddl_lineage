import {createRoot} from 'react-dom/client';
import React from 'react';
import {configure} from '@gravity-ui/uikit';
import {App} from './App';

configure({lang: 'en'});

const mountNode = document.getElementById('root');
if (!mountNode) {
    throw new Error('Root element not found');
}

const root = createRoot(mountNode);
root.render(
    <React.StrictMode>
        <App />
    </React.StrictMode>,
);
