import {Clock} from '@gravity-ui/icons';
import {Icon, Spin} from '@gravity-ui/uikit';
import React from 'react';

import {CompareModal} from './CompareModal';
import {ProjectHistoryEntry} from './types';

interface Props {
    projectName: string;
    onRestoreVersion: (name: string, id: number) => Promise<void>;
}

export const HistoryPanel: React.FC<Props> = ({projectName, onRestoreVersion}) => {
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
                <h3>Analysis History</h3>
                {projectName && (
                    <button
                        type="button"
                        className="side-panel__add"
                        title="Refresh"
                        onClick={refresh}
                        disabled={loading}
                    >
                        {loading ? <Spin size="xs" /> : '↻'}
                    </button>
                )}
            </div>

            <div className="side-panel__body">
                {!projectName ? (
                    <div className="side-panel__empty">
                        Open a project to see its analysis history.
                    </div>
                ) : loading ? (
                    <div className="side-panel__empty">
                        <Spin size="s" />
                    </div>
                ) : history.length === 0 ? (
                    <div className="side-panel__empty">
                        No saved analyses yet. Run Analyze to create the first version.
                    </div>
                ) : (
                    <>
                        <div className="side-panel__section">
                            <div className="side-panel__section-title">
                                {projectName}
                                <span className="panel-count">{history.length}</span>
                            </div>
                        </div>

                        {history.length >= 2 && (
                            <div className="history-hint">
                                Select 2 versions to compare
                            </div>
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
                                                aria-label={`Select version ${history.length - index}`}
                                            />
                                        )}
                                        <div className="version-item__meta">
                                            <span className="version-item__label">
                                                v{history.length - index}
                                            </span>
                                            <span className="version-item__time">
                                                <Icon data={Clock} size={11} />
                                                {formatRelativeDate(entry.timestamp)}
                                            </span>
                                            {entry.summary.total_objects !== undefined && (
                                                <span className="version-item__stats">
                                                    {entry.summary.total_objects} objects
                                                    {entry.summary.total_edges !== undefined
                                                        ? ` · ${entry.summary.total_edges} edges`
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
                                                'Restore'
                                            )}
                                        </button>
                                    </div>
                                );
                            })}
                        </div>

                        {selectedIds.length === 2 && compareVersions && (
                            <div className="history-compare-bar">
                                <span className="history-compare-bar__label">
                                    v{history.length - history.findIndex((h) => h.id === selectedIds[0])} vs v{history.length - history.findIndex((h) => h.id === selectedIds[1])}
                                </span>
                                <button
                                    type="button"
                                    className="history-compare-bar__btn"
                                    onClick={() => setCompareOpen(true)}
                                >
                                    Compare
                                </button>
                                <button
                                    type="button"
                                    className="history-compare-bar__clear"
                                    onClick={() => setSelectedIds([])}
                                    title="Clear selection"
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

function formatRelativeDate(isoString: string): string {
    try {
        const diff = Date.now() - new Date(isoString).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return `${mins}m ago`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours}h ago`;
        return `${Math.floor(hours / 24)}d ago`;
    } catch {
        return '';
    }
}
