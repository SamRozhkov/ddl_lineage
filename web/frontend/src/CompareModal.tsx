import {Modal, Spin} from '@gravity-ui/uikit';
import React from 'react';

import {AnalysisResult, ProjectHistoryEntry} from './types';

interface Props {
    open: boolean;
    onClose: () => void;
    projectName: string;
    versionA: ProjectHistoryEntry; // newer (higher index, lower id in list)
    versionB: ProjectHistoryEntry; // older
}

type DiffStatus = 'added' | 'removed' | 'unchanged';

interface ObjectDiff {
    key: string;
    type: string;
    status: DiffStatus;
    columnsA?: number;
    columnsB?: number;
}

interface EdgeDiff {
    key: string;
    source: string;
    target: string;
    edgeType: string;
    status: DiffStatus;
}

function computeDiff(a: AnalysisResult, b: AnalysisResult) {
    // Objects diff (a = newer, b = older)
    const keysB = new Map(b.objects.map((o) => [`${o.type}::${o.schema ?? ''}::${o.name}`, o]));
    const keysA = new Map(a.objects.map((o) => [`${o.type}::${o.schema ?? ''}::${o.name}`, o]));

    const objects: ObjectDiff[] = [];
    keysA.forEach((obj, key) => {
        objects.push({
            key,
            type: obj.type,
            status: keysB.has(key) ? 'unchanged' : 'added',
            columnsA: obj.columns.length,
            columnsB: keysB.get(key)?.columns.length,
        });
    });
    keysB.forEach((obj, key) => {
        if (!keysA.has(key)) {
            objects.push({
                key,
                type: obj.type,
                status: 'removed',
                columnsB: obj.columns.length,
            });
        }
    });

    // Sort: added first, then removed, then unchanged
    const order: Record<DiffStatus, number> = {added: 0, removed: 1, unchanged: 2};
    objects.sort((x, y) => order[x.status] - order[y.status] || x.key.localeCompare(y.key));

    // Edges diff
    const edgeKey = (e: {source: string; target: string; type: string}) =>
        `${e.source}→${e.target}::${e.type}`;
    const edgesB = new Set(b.edges.map(edgeKey));
    const edgesA = new Set(a.edges.map(edgeKey));

    const edges: EdgeDiff[] = [];
    a.edges.forEach((e) => {
        const k = edgeKey(e);
        edges.push({key: k, source: e.source, target: e.target, edgeType: e.type, status: edgesB.has(k) ? 'unchanged' : 'added'});
    });
    b.edges.forEach((e) => {
        const k = edgeKey(e);
        if (!edgesA.has(k)) {
            edges.push({key: k, source: e.source, target: e.target, edgeType: e.type, status: 'removed'});
        }
    });
    edges.sort((x, y) => order[x.status] - order[y.status] || x.key.localeCompare(y.key));

    return {objects, edges};
}

export const CompareModal: React.FC<Props> = ({open, onClose, projectName, versionA, versionB}) => {
    const [loading, setLoading] = React.useState(false);
    const [analysisA, setAnalysisA] = React.useState<AnalysisResult | null>(null);
    const [analysisB, setAnalysisB] = React.useState<AnalysisResult | null>(null);
    const [error, setError] = React.useState('');

    React.useEffect(() => {
        if (!open) return;
        setLoading(true);
        setError('');
        setAnalysisA(null);
        setAnalysisB(null);

        const fetchEntry = (id: number) =>
            fetch(`/api/project/${encodeURIComponent(projectName)}/history/${id}`)
                .then((r) => r.json())
                .then((p) => {
                    if (!p.success) throw new Error(p.error || 'Load failed');
                    return (p.project?.analysis ?? null) as AnalysisResult | null;
                });

        Promise.all([fetchEntry(versionA.id), fetchEntry(versionB.id)])
            .then(([a, b]) => {
                setAnalysisA(a);
                setAnalysisB(b);
            })
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, [open, projectName, versionA.id, versionB.id]);

    const diff = analysisA && analysisB ? computeDiff(analysisA, analysisB) : null;

    const addedObjects = diff?.objects.filter((o) => o.status === 'added').length ?? 0;
    const removedObjects = diff?.objects.filter((o) => o.status === 'removed').length ?? 0;
    const addedEdges = diff?.edges.filter((e) => e.status === 'added').length ?? 0;
    const removedEdges = diff?.edges.filter((e) => e.status === 'removed').length ?? 0;

    const indexA = versionA.id;
    const indexB = versionB.id;

    return (
        <Modal open={open} onClose={onClose} contentOverflow="auto">
            <div className="compare-modal">
                <div className="compare-modal__header">
                    <div className="compare-modal__title">Version comparison</div>
                    <div className="compare-modal__versions">
                        <span className="compare-ver compare-ver--a">
                            #{indexA} &nbsp;{formatDate(versionA.timestamp)}
                        </span>
                        <span className="compare-arrow">vs</span>
                        <span className="compare-ver compare-ver--b">
                            #{indexB} &nbsp;{formatDate(versionB.timestamp)}
                        </span>
                    </div>
                    <button type="button" className="compare-modal__close" onClick={onClose}>
                        ✕
                    </button>
                </div>

                <div className="compare-modal__body">
                    {loading && (
                        <div className="compare-modal__loading">
                            <Spin size="m" />
                        </div>
                    )}

                    {error && <div className="compare-modal__error">{error}</div>}

                    {diff && (
                        <>
                            {/* Stats bar */}
                            <div className="compare-stats">
                                {addedObjects > 0 && (
                                    <span className="compare-chip compare-chip--added">
                                        +{addedObjects} object{addedObjects !== 1 ? 's' : ''}
                                    </span>
                                )}
                                {removedObjects > 0 && (
                                    <span className="compare-chip compare-chip--removed">
                                        −{removedObjects} object{removedObjects !== 1 ? 's' : ''}
                                    </span>
                                )}
                                {addedEdges > 0 && (
                                    <span className="compare-chip compare-chip--added">
                                        +{addedEdges} edge{addedEdges !== 1 ? 's' : ''}
                                    </span>
                                )}
                                {removedEdges > 0 && (
                                    <span className="compare-chip compare-chip--removed">
                                        −{removedEdges} edge{removedEdges !== 1 ? 's' : ''}
                                    </span>
                                )}
                                {addedObjects === 0 && removedObjects === 0 && addedEdges === 0 && removedEdges === 0 && (
                                    <span className="compare-chip">No structural changes</span>
                                )}
                            </div>

                            {/* Objects */}
                            <div className="compare-section-title">Objects</div>
                            <div className="table-wrap">
                                <table>
                                    <thead>
                                        <tr>
                                            <th></th>
                                            <th>Name</th>
                                            <th>Type</th>
                                            <th>Columns (new)</th>
                                            <th>Columns (old)</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {diff.objects.map((obj) => {
                                            const [, schema, name] = obj.key.split('::');
                                            const displayName = schema ? `${schema}.${name}` : name;
                                            return (
                                                <tr
                                                    key={obj.key}
                                                    className={`diff-row diff-row--${obj.status}`}
                                                >
                                                    <td className="diff-status">
                                                        {obj.status === 'added' ? '+' : obj.status === 'removed' ? '−' : ''}
                                                    </td>
                                                    <td>{displayName}</td>
                                                    <td>
                                                        <span className={`edge type-${obj.type.toLowerCase()}`}>
                                                            {obj.type}
                                                        </span>
                                                    </td>
                                                    <td>{obj.columnsA ?? '—'}</td>
                                                    <td>{obj.columnsB ?? '—'}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>

                            {/* Edges */}
                            {(diff.edges.length > 0) && (
                                <>
                                    <div className="compare-section-title">Edges</div>
                                    <div className="table-wrap">
                                        <table>
                                            <thead>
                                                <tr>
                                                    <th></th>
                                                    <th>Source</th>
                                                    <th>Type</th>
                                                    <th>Target</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {diff.edges.map((edge) => (
                                                    <tr
                                                        key={edge.key}
                                                        className={`diff-row diff-row--${edge.status}`}
                                                    >
                                                        <td className="diff-status">
                                                            {edge.status === 'added' ? '+' : edge.status === 'removed' ? '−' : ''}
                                                        </td>
                                                        <td>{edge.source}</td>
                                                        <td>
                                                            <span className={`edge edge-${edge.edgeType.toLowerCase()}`}>
                                                                {edge.edgeType}
                                                            </span>
                                                        </td>
                                                        <td>{edge.target}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </>
                            )}
                        </>
                    )}
                </div>
            </div>
        </Modal>
    );
};

function formatDate(iso: string): string {
    try {
        return new Date(iso).toLocaleString(undefined, {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch {
        return iso;
    }
}
