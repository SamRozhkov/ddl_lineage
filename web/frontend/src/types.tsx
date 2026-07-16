import type {TBlock} from '@gravity-ui/graph';

export type DDLObject = {
    name: string;
    type: string;
    schema: string;
    temporary?: boolean;
    columns: Array<{
        name: string;
        type: string;
        nullable: boolean;
        pk: boolean;
        fk_to: string;
        unique: boolean;
        default: string;
    }>;
};

export type LineageEdge = {
    source: string;
    target: string;
    type: string;
    via: string;
    details: string;
};

export type AnalysisResult = {
    objects: DDLObject[];
    edges: LineageEdge[];
    cycles: string[][];
    topo_order: string[];
    stats: {
        total_objects: number;
        total_edges: number;
        has_cycles: boolean;
    };
};

export type AnalyzeResponse = {
    success: boolean;
    data?: AnalysisResult;
    mermaid?: string;
    error?: string | null;
};

export type ProjectHistoryEntry = {
    id: number;
    timestamp: string;
    action: string;
    summary: {
        total_objects?: number;
        total_edges?: number;
    };
};

export type ProjectSummary = {
    project_name: string;
    display_name: string;
    description: string;
    updated_at: string;
    has_state: boolean;
};

export type GraphFieldMeta = {
    name: string;
    type: string;
};

export type GraphBlockMeta = {
    objectType: string;
    schema: string;
    columns: number;
    fields: GraphFieldMeta[];
    temporary: boolean;
};

export type LineageGraphBlock = TBlock<GraphBlockMeta>;

export type SavedConnection = {
    id: string;
    name: string;
    type: 'postgresql' | 'mysql';
    host: string;
    port: string;
    database: string;
    schema: string;
    username: string;
};

export type ConnectFormData = {
    name: string;
    type: string;
    host: string;
    port: string;
    database: string;
    schema: string;
    username: string;
    password: string;
};