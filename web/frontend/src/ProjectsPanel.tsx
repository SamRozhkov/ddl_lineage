import {Clock, TrashBin} from '@gravity-ui/icons';
import {Icon, Spin, TextInput} from '@gravity-ui/uikit';
import React from 'react';

import {ProjectSummary} from './types';

interface Props {
    projects: ProjectSummary[];
    projectName: string;
    onProjectNameChange: (name: string) => void;
    onLoad: (name: string) => void;
    onDelete: (name: string) => Promise<void>;
}

export const ProjectsPanel: React.FC<Props> = ({
    projects,
    projectName,
    onProjectNameChange,
    onLoad,
    onDelete,
}) => {
    const [deletingId, setDeletingId] = React.useState<string | null>(null);

    const handleDelete = async (name: string, e: React.MouseEvent) => {
        e.stopPropagation();
        setDeletingId(name);
        try {
            await onDelete(name);
        } finally {
            setDeletingId(null);
        }
    };

    return (
        <div className="side-panel">
            <div className="side-panel__header">
                <h3>Projects</h3>
            </div>

            <div className="side-panel__body">
                {/* Active project section */}
                <div className="side-panel__section">
                    <div className="side-panel__section-title">Active project</div>
                    <div className="side-panel__project-input">
                        <TextInput
                            value={projectName}
                            onUpdate={onProjectNameChange}
                            placeholder="Enter project name…"
                            size="m"
                        />
                    </div>
                    <p className="side-panel__hint">
                        {projectName
                            ? 'Results will be saved to this project on each Analyze.'
                            : 'Set a name to auto-save analysis results.'}
                    </p>
                </div>

                {/* Saved projects list */}
                {projects.length > 0 && (
                    <>
                        <div className="side-panel__divider" />
                        <div className="side-panel__section">
                            <div className="side-panel__section-title">
                                Saved projects
                                <span className="panel-count">{projects.length}</span>
                            </div>
                        </div>
                        <div className="project-list">
                            {projects.map((project) => (
                                <div
                                    key={project.project_name}
                                    className={`project-item${projectName === project.project_name ? ' project-item--active' : ''}`}
                                    onClick={() => onLoad(project.project_name)}
                                    role="button"
                                    tabIndex={0}
                                    onKeyDown={(e) =>
                                        e.key === 'Enter' && onLoad(project.project_name)
                                    }
                                >
                                    <div className="project-item__main">
                                        <span className="project-item__name">
                                            {project.display_name}
                                        </span>
                                        {project.updated_at && (
                                            <span className="project-item__date">
                                                <Icon data={Clock} size={11} />
                                                {formatRelativeDate(project.updated_at)}
                                            </span>
                                        )}
                                    </div>
                                    <button
                                        type="button"
                                        className="project-item__delete"
                                        title="Delete project"
                                        onClick={(e) => void handleDelete(project.project_name, e)}
                                        disabled={deletingId === project.project_name}
                                    >
                                        {deletingId === project.project_name ? (
                                            <Spin size="xs" />
                                        ) : (
                                            <Icon data={TrashBin} size={14} />
                                        )}
                                    </button>
                                </div>
                            ))}
                        </div>
                    </>
                )}

                {projects.length === 0 && !projectName && (
                    <div className="side-panel__empty">
                        No saved projects yet. Set a project name and run Analyze to create one.
                    </div>
                )}
            </div>
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
