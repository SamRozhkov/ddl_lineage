import {CirclePlay, Plus, TrashBin} from '@gravity-ui/icons';
import {Icon, PasswordInput, Select, Spin, TextInput} from '@gravity-ui/uikit';
import React from 'react';

import {useI18n} from './i18n';
import {ConnectFormData, SavedConnection} from './types';

const DEFAULT_FORM: ConnectFormData = {
    name: '',
    type: 'postgresql',
    host: 'localhost',
    port: '5432',
    database: '',
    schema: 'public',
    username: '',
    password: '',
};

interface Props {
    savedConnections: SavedConnection[];
    scanning: boolean;
    scanError: string;
    onScan: (form: ConnectFormData) => Promise<void>;
    onSave: (conn: SavedConnection) => void;
    onDelete: (id: string) => void;
}

export const ConnectionsPanel: React.FC<Props> = ({
    savedConnections,
    scanning,
    scanError,
    onScan,
    onSave,
    onDelete,
}) => {
    const {t} = useI18n();
    const [showForm, setShowForm] = React.useState(savedConnections.length === 0);
    const [form, setForm] = React.useState<ConnectFormData>(DEFAULT_FORM);

    const update = (field: keyof ConnectFormData) => (value: string) =>
        setForm((prev) => ({...prev, [field]: value}));

    const handleTypeChange = ([val]: string[]) => {
        setForm((prev) => ({...prev, type: val, port: val === 'mysql' ? '3306' : '5432'}));
    };

    const loadIntoForm = (conn: SavedConnection) => {
        setForm({
            name: conn.name,
            type: conn.type,
            host: conn.host,
            port: conn.port,
            database: conn.database,
            schema: conn.schema,
            username: conn.username,
            password: '',
        });
        setShowForm(true);
    };

    const handleSave = () => {
        const conn: SavedConnection = {
            id: String(Date.now()),
            name: form.name.trim() || `${form.database}@${form.host}`,
            type: form.type as 'postgresql' | 'mysql',
            host: form.host,
            port: form.port,
            database: form.database,
            schema: form.schema,
            username: form.username,
        };
        onSave(conn);
        if (savedConnections.length > 0) setShowForm(false);
    };

    const canScan = !scanning && !!form.host && !!form.database && !!form.username && !!form.password;

    return (
        <div className="side-panel">
            <div className="side-panel__header">
                <h3>{t('connections.title')}</h3>
                {!showForm && (
                    <button
                        type="button"
                        className="side-panel__add"
                        onClick={() => {
                            setForm(DEFAULT_FORM);
                            setShowForm(true);
                        }}
                    >
                        <Icon data={Plus} size={14} />
                        {t('connections.new')}
                    </button>
                )}
            </div>

            <div className="side-panel__body">
                {!showForm && savedConnections.length > 0 && (
                    <div className="conn-list">
                        {savedConnections.map((conn) => (
                            <div key={conn.id} className="conn-item">
                                <div
                                    className="conn-item__info"
                                    role="button"
                                    tabIndex={0}
                                    onClick={() => loadIntoForm(conn)}
                                    onKeyDown={(e) => e.key === 'Enter' && loadIntoForm(conn)}
                                >
                                    <span className="conn-item__name">{conn.name}</span>
                                    <span className="conn-item__meta">
                                        <span className={`edge type-${conn.type}`}>{conn.type}</span>
                                        &nbsp;{conn.host}:{conn.port} / {conn.database}
                                    </span>
                                </div>
                                <div className="conn-item__actions">
                                    <button
                                        type="button"
                                        className="conn-item__btn"
                                        title={t('connections.editScanTitle')}
                                        onClick={() => loadIntoForm(conn)}
                                    >
                                        <Icon data={CirclePlay} size={16} />
                                    </button>
                                    <button
                                        type="button"
                                        className="conn-item__btn conn-item__btn--danger"
                                        title={t('connections.removeTitle')}
                                        onClick={() => onDelete(conn.id)}
                                    >
                                        <Icon data={TrashBin} size={14} />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {!showForm && savedConnections.length === 0 && (
                    <div className="side-panel__empty">
                        {t('connections.empty')}
                        <button
                            type="button"
                            className="btn-link"
                            onClick={() => {
                                setForm(DEFAULT_FORM);
                                setShowForm(true);
                            }}
                        >
                            {t('connections.addFirst')}
                        </button>
                    </div>
                )}

                {showForm && (
                    <div className="conn-form">
                        <div className="conn-form__field">
                            <label className="conn-form__label">{t('connections.form.name')}</label>
                            <TextInput
                                value={form.name}
                                onUpdate={update('name')}
                                placeholder={t('connections.form.namePlaceholder')}
                                size="m"
                            />
                        </div>

                        <div className="conn-form__field">
                            <label className="conn-form__label">{t('connections.form.dbType')}</label>
                            <Select
                                value={[form.type]}
                                onUpdate={handleTypeChange}
                                options={[
                                    {value: 'postgresql', content: 'PostgreSQL'},
                                    {value: 'mysql', content: 'MySQL / MariaDB'},
                                ]}
                                width="max"
                                size="m"
                            />
                        </div>

                        <div className="conn-form__row">
                            <div className="conn-form__field conn-form__field--grow">
                                <label className="conn-form__label">{t('connections.form.host')}</label>
                                <TextInput
                                    value={form.host}
                                    onUpdate={update('host')}
                                    placeholder="localhost"
                                    size="m"
                                />
                            </div>
                            <div className="conn-form__field conn-form__field--port">
                                <label className="conn-form__label">{t('connections.form.port')}</label>
                                <TextInput
                                    value={form.port}
                                    onUpdate={update('port')}
                                    placeholder="5432"
                                    size="m"
                                />
                            </div>
                        </div>

                        <div className="conn-form__field">
                            <label className="conn-form__label">{t('connections.form.database')}</label>
                            <TextInput
                                value={form.database}
                                onUpdate={update('database')}
                                placeholder={t('connections.form.databasePlaceholder')}
                                size="m"
                            />
                        </div>

                        {form.type === 'postgresql' && (
                            <div className="conn-form__field">
                                <label className="conn-form__label">{t('connections.form.schema')}</label>
                                <TextInput
                                    value={form.schema}
                                    onUpdate={update('schema')}
                                    placeholder="public"
                                    size="m"
                                />
                            </div>
                        )}

                        <div className="conn-form__field">
                            <label className="conn-form__label">{t('connections.form.username')}</label>
                            <TextInput
                                value={form.username}
                                onUpdate={update('username')}
                                placeholder="postgres"
                                size="m"
                            />
                        </div>

                        <div className="conn-form__field">
                            <label className="conn-form__label">{t('connections.form.password')}</label>
                            <PasswordInput
                                value={form.password}
                                onUpdate={update('password')}
                                placeholder="••••••••"
                                size="m"
                            />
                            <span className="conn-form__hint">{t('connections.form.passwordHint')}</span>
                        </div>

                        {scanError && <div className="conn-form__error">{scanError}</div>}

                        <div className="conn-form__actions">
                            {savedConnections.length > 0 && (
                                <button
                                    type="button"
                                    className="btn-secondary"
                                    onClick={() => setShowForm(false)}
                                >
                                    {t('connections.form.cancel')}
                                </button>
                            )}
                            <button
                                type="button"
                                className="btn-secondary"
                                disabled={!form.host || !form.database || !form.username}
                                onClick={handleSave}
                            >
                                {t('connections.form.save')}
                            </button>
                            <button
                                type="button"
                                className="btn-scan"
                                disabled={!canScan}
                                onClick={() => void onScan(form)}
                            >
                                {scanning ? (
                                    <>
                                        <Spin size="xs" />
                                        {t('connections.form.scanning')}
                                    </>
                                ) : (
                                    <>
                                        <Icon data={CirclePlay} size={14} />
                                        {t('connections.form.scan')}
                                    </>
                                )}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};
