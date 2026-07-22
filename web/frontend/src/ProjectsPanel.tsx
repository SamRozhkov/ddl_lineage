import {Clock, TrashBin} from '@gravity-ui/icons';
import {Icon, Spin, TextInput} from '@gravity-ui/uikit';
import React from 'react';

import {formatRelativeTime, useI18n} from './i18n';
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
    const {t} = useI18n();
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
                <h3>{t('projects.title')}</h3>
            </div>

            <div className="side-panel__body">
                <div className="side-panel__section">
                    <div className="side-panel__section-title">{t('projects.activeProject')}</div>
                    <div className="side-panel__project-input">
                        <TextInput
                            value={projectName}
                            onUpdate={onProjectNameChange}
                            placeholder={t('projects.namePlaceholder')}
                            size="m"
                        />
                    </div>
                    <p className="side-panel__hint">
                        {projectName ? t('projects.hintSet') : t('projects.hintUnset')}
                    </p>
                </div>

                {projects.length > 0 && (
                    <>
                        <div className="side-panel__divider" />
                        <div className="side-panel__section">
                            <div className="side-panel__section-title">
                                {t('projects.saved')}
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
                                                {formatRelativeTime(project.updated_at, t)}
                                            </span>
                                        )}
                                    </div>
                                    <button
                                        type="button"
                                        className="project-item__delete"
                                        title={t('projects.deleteTitle')}
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
                    <div className="side-panel__empty">{t('projects.empty')}</div>
                )}
            </div>
        </div>
    );
};
