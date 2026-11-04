export interface LifecycleStateDefinition {
    graphid: string;
    lifecycle_state_id: string;
}

export interface LifecycleState {
    id: string;
    name: string;
}

export interface ResourceModel {
    graphid: string;
    name: string;
    lifecycle_states: LifecycleState[];
}
