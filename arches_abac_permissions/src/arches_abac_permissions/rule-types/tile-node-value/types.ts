export interface TileNodeValueDefinition {
    graphid: string;
    nodeid: string;
    value: string;
    language: string;
}

export interface ResourceModel {
    graphid: string;
    name: string;
}

export interface NodeOption {
    id: string;
    label: string;
}

export interface TileNode {
    nodeid: string;
    name: string;
    alias: string;
    datatype: string;
    options?: NodeOption[];
    true_label?: string;
    false_label?: string;
    date_format?: string;
    controlled_list_id?: string | null;
}

export interface Language {
    code: string;
    name: string;
}

export interface ListItemOption extends NodeOption {
    depth: number;
}
