import {Clock} from '@gravity-ui/icons';
import {Icon, Spin} from '@gravity-ui/uikit';
import React from 'react';

import {CompareModal} from './CompareModal';
import {formatRelativeTime, useI18n} from './i18n';
import {ProjectHistoryEntry} from './types';

interface Props {
    projectName: string;
    onRestoreVersion: (name: string, id: number) => Promise<void>;
}

export const HistoryPanel: React.FC<Props> = ({projectName, onRestoreVersion}) => {
    const {t, plural} = useI18n();
    const [history, setHistory] = React.useState<ProjectHistoryEntry[]>([]);
    const [loading, setLoading] = React.useState(false);
    const [restoringId, setRestoringId] = React.useState<number | null>(null);
    const [selectedIds, setSelectedIds] = React.useState<number[]>([]);
    const [compareOpen, setCompareOpen] = React.useState(false);

    const refresh = React.useCallback(() => {
        if (!projectName) {
            setHistory([]);
            return;
        }
        setLoading(true);
        fetch(`/api/project/${encodeURIComponent(projectName)}/history`)
            .then((r) => r.json())
            .then((payload) => {
                if (payload.success) {
                    setHistory(
                        (payload.history || []).filter(
                            (h: ProjectHistoryEntry) => h.action === 'analysis',
                        ),
                    );
                }
            })
            .catch(() => setHistory([]))
            .finally(() => setLoading(false));
    }, [projectName]);

    React.useEffect(() => {
        setSelectedIds([]);
        refresh();
    }, [refresh]);

    const handleRestore = async (id: number) => {
        setRestoringId(id);
        try {
            await onRestoreVersion(projectName, id);
        } finally {
            setRestoringId(null);
        }
    };

    const toggleSelect = (id: number) => {
        setSelectedIds((prev) => {
            if (prev.includes(id)) return prev.filter((x) => x !== id);
            if (prev.length >= 2) return [prev[1], id]; // sliding window of 2
            return [...prev, id];
        });
    };

    const compareVersions =
        selectedIds.length === 2
            ? {
                  a: history.find((h) => h.id === selectedIds[0])!,
                  b: history.find((h) => h.id === selectedIds[1])!,
              }
            : null;

    return (
        <div className="side-panel">
            <div className="side-panel__header">
                <h3>{t('history.title')}</h3>
                {projectName && (
                    <button
                        type="button"
                        className="side-panel__add"
                        title={t('history.refreshTitle')}
                        onClick={refresh}
                        disabled={loading}
                    >
                        {loading ? <Spin size="xs" /> : '↻'}
                    </button>
                )}
            </div>

            <div className="side-panel__body">
                {!projectName ? (
                    <div className="side-panel__empty">{t('history.openProjectHint')}</div>
                ) : loading ? (
                    <div className="side-panel__empty">
                        <Spin size="s" />
                    </div>
                ) : history.length === 0 ? (
                    <div className="side-panel__empty">{t('history.empty')}</div>
                ) : (
                    <>
                        <div className="side-panel__section">
                            <div className="side-panel__section-title">
                                {projectName}
                                <span className="panel-count">{history.length}</span>
                            </div>
                        </div>

                        {history.length >= 2 && (
                            <div className="history-hint">{t('history.selectHint')}</div>
                        )}

                        <div className="version-list">
                            {history.map((entry, index) => {
                                const isSelected = selectedIds.includes(entry.id);
                                return (
                                    <div
                                        key={entry.id}
                                        className={`version-item${isSelected ? ' version-item--selected' : ''}`}
                                    >
                                        {history.length >= 2 && (
                                            <input
                                                type="checkbox"
                                                className="version-item__check"
                                                checked={isSelected}
                                                onChange={() => toggleSelect(entry.id)}
                                                aria-label={t('history.selectVersion', {v: history.length - index})}
                                            />
                                        )}
                                        <div className="version-item__meta">
                                            <span className="version-item__label">
                                                v{history.length - index}
                                            </span>
                                            <span className="version-item__time">
                                                <Icon data={Clock} size={11} />
                                                {formatRelativeTime(entry.timestamp, t)}
                                            </span>
                                            {entry.summary.total_objects !== undefined && (
                                                <span className="version-item__stats">
                                                    {entry.summary.total_objects}{' '}
                                                    {plural(entry.summary.total_objects, 'object')}
                                                    {entry.summary.total_edges !== undefined
                                                        ? ` · ${entry.summary.total_edges} ${plural(entry.summary.total_edges, 'edge')}`
                                                        : ''}
                                                </span>
                                            )}
                                        </div>
                                        <button
                                            type="button"
                                            className="version-item__restore"
                                            disabled={restoringId === entry.id}
                                            onClick={() => void handleRestore(entry.id)}
                                        >
                                            {restoringId === entry.id ? (
                                                <Spin size="xs" />
                                            ) : (
                                                t('history.restore')
                                            )}
                                        </button>
                                    </div>
                                );
                            })}
                        </div>

                        {selectedIds.length === 2 && compareVersions && (
                            <div className="history-compare-bar">
                                <span className="history-compare-bar__label">
                                    {t('history.compareLabel', {
                                        a: history.length - history.findIndex((h) => h.id === selectedIds[0]),
                                        b: history.length - history.findIndex((h) => h.id === selectedIds[1]),
                                    })}
                                </span>
                                <button
                                    type="button"
                                    className="history-compare-bar__btn"
                                    onClick={() => setCompareOpen(true)}
                                >
                                    {t('history.compareBtn')}
                                </button>
                                <button
                                    type="button"
                                    className="history-compare-bar__clear"
                                    onClick={() => setSelectedIds([])}
                                    title={t('history.clearTitle')}
                                >
                                    ✕
                                </button>
                            </div>
                        )}
                    </>
                )}
            </div>

            {compareVersions && (
                <CompareModal
                    open={compareOpen}
                    onClose={() => setCompareOpen(false)}
                    projectName={projectName}
                    versionA={compareVersions.a}
                    versionB={compareVersions.b}
                />
            )}
        </div>
    );
};
