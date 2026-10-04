"""Frozen wire descriptions for retired JIT routes.

These schemas are documentation only: handlers accept arbitrary old requests and
always return 410. Keeping the released success shape protects generated clients
and the directional contract checker without executing auth or body validation.
"""

TRIGGER_FEEDBACK_OPENAPI = {
    'parameters': [
        {
            'in': 'header',
            'name': 'authorization',
            'required': False,
            'schema': {'title': 'Authorization', 'type': 'string'},
        },
        {
            'in': 'header',
            'name': 'X-App-Platform',
            'required': False,
            'schema': {'title': 'X-App-Platform', 'type': 'string'},
        },
        {
            'in': 'header',
            'name': 'X-Device-Id-Hash',
            'required': False,
            'schema': {'title': 'X-Device-Id-Hash', 'type': 'string'},
        },
        {
            'in': 'header',
            'name': 'X-App-Version',
            'required': False,
            'schema': {'title': 'X-App-Version', 'type': 'string'},
        },
    ],
    'requestBody': {
        'content': {
            'application/json': {
                'schema': {
                    'additionalProperties': False,
                    'properties': {
                        'account_generation': {'minimum': 0.0, 'title': 'Account ' 'Generation', 'type': 'integer'},
                        'action': {
                            'enum': ['useful', 'false_positive', 'snooze', 'disable', 'missed_or_late'],
                            'title': 'Action',
                            'type': 'string',
                        },
                        'event_id': {'pattern': '^[0-9a-f]{64}$', 'title': 'Event Id', 'type': 'string'},
                        'feedback_id': {'pattern': '^[0-9a-f]{64}$', 'title': 'Feedback ' 'Id', 'type': 'string'},
                        'recorded_at': {'format': 'date-time', 'title': 'Recorded ' 'At', 'type': 'string'},
                        'snoozed_until': {
                            'anyOf': [{'format': 'date-time', 'type': 'string'}, {'type': 'null'}],
                            'title': 'Snoozed ' 'Until',
                        },
                        'trigger_memory_id': {
                            'maxLength': 256,
                            'minLength': 1,
                            'pattern': '^[^/]+$',
                            'title': 'Trigger ' 'Memory ' 'Id',
                            'type': 'string',
                        },
                        'trigger_revision': {'minimum': 1.0, 'title': 'Trigger ' 'Revision', 'type': 'integer'},
                    },
                    'required': [
                        'feedback_id',
                        'event_id',
                        'trigger_memory_id',
                        'account_generation',
                        'trigger_revision',
                        'action',
                        'recorded_at',
                    ],
                    'title': 'JITTriggerFeedbackRequest',
                    'type': 'object',
                }
            }
        },
        'required': True,
    },
    'responses': {
        '200': {
            'content': {
                'application/json': {
                    'schema': {
                        'additionalProperties': False,
                        'properties': {
                            'applied': {'title': 'Applied', 'type': 'boolean'},
                            'receipt': {
                                'additionalProperties': False,
                                'properties': {
                                    'account_generation': {
                                        'minimum': 0.0,
                                        'title': 'Account ' 'Generation',
                                        'type': 'integer',
                                    },
                                    'action': {
                                        'enum': ['useful', 'false_positive', 'snooze', 'disable', 'missed_or_late'],
                                        'title': 'Action',
                                        'type': 'string',
                                    },
                                    'applied_trigger_revision': {
                                        'anyOf': [{'minimum': 1.0, 'type': 'integer'}, {'type': 'null'}],
                                        'title': 'Applied ' 'Trigger ' 'Revision',
                                    },
                                    'event_id': {'pattern': '^[0-9a-f]{64}$', 'title': 'Event ' 'Id', 'type': 'string'},
                                    'expected_trigger_revision': {
                                        'minimum': 1.0,
                                        'title': 'Expected ' 'Trigger ' 'Revision',
                                        'type': 'integer',
                                    },
                                    'feedback_id': {
                                        'pattern': '^[0-9a-f]{64}$',
                                        'title': 'Feedback ' 'Id',
                                        'type': 'string',
                                    },
                                    'recorded_at': {'format': 'date-time', 'title': 'Recorded ' 'At', 'type': 'string'},
                                    'request_hash': {
                                        'pattern': '^[0-9a-f]{64}$',
                                        'title': 'Request ' 'Hash',
                                        'type': 'string',
                                    },
                                    'schema_version': {
                                        'const': 'jit_trigger_feedback.v1',
                                        'default': 'jit_trigger_feedback.v1',
                                        'title': 'Schema ' 'Version',
                                        'type': 'string',
                                    },
                                    'snoozed_until': {
                                        'anyOf': [{'format': 'date-time', 'type': 'string'}, {'type': 'null'}],
                                        'title': 'Snoozed ' 'Until',
                                    },
                                    'trigger_memory_id': {'title': 'Trigger ' 'Memory ' 'Id', 'type': 'string'},
                                    'uid': {'title': 'Uid', 'type': 'string'},
                                },
                                'required': [
                                    'uid',
                                    'feedback_id',
                                    'event_id',
                                    'trigger_memory_id',
                                    'account_generation',
                                    'expected_trigger_revision',
                                    'action',
                                    'recorded_at',
                                    'request_hash',
                                ],
                                'title': 'JITTriggerFeedbackReceipt',
                                'type': 'object',
                            },
                            'trigger_memory_id': {'title': 'Trigger ' 'Memory ' 'Id', 'type': 'string'},
                            'trigger_revision': {'minimum': 1.0, 'title': 'Trigger ' 'Revision', 'type': 'integer'},
                            'trigger_status': {'title': 'Trigger ' 'Status', 'type': 'string'},
                        },
                        'required': ['applied', 'trigger_memory_id', 'trigger_revision', 'trigger_status', 'receipt'],
                        'title': 'JITTriggerFeedbackEnvelope',
                        'type': 'object',
                    }
                }
            },
            'description': 'Historical success schema only. This retired endpoint always returns ' '410.',
        },
        '401': {
            'content': {
                'application/json': {
                    'schema': {
                        'properties': {
                            'detail': {
                                'anyOf': [{'type': 'string'}, {'type': 'array'}, {'type': 'object'}],
                                'description': 'Error ' 'detail ' 'returned ' 'by ' 'the ' 'API.',
                            }
                        },
                        'required': ['detail'],
                        'title': 'ErrorResponse',
                        'type': 'object',
                    }
                }
            },
            'description': 'Missing or invalid authentication credentials.',
        },
        '422': {
            'content': {
                'application/json': {
                    'schema': {
                        'properties': {
                            'detail': {
                                'items': {
                                    'properties': {
                                        'loc': {
                                            'items': {'anyOf': [{'type': 'string'}, {'type': 'integer'}]},
                                            'title': 'Location',
                                            'type': 'array',
                                        },
                                        'msg': {'title': 'Message', 'type': 'string'},
                                        'type': {'title': 'Error ' 'Type', 'type': 'string'},
                                    },
                                    'required': ['loc', 'msg', 'type'],
                                    'title': 'ValidationError',
                                    'type': 'object',
                                },
                                'title': 'Detail',
                                'type': 'array',
                            }
                        },
                        'title': 'HTTPValidationError',
                        'type': 'object',
                    }
                }
            },
            'description': 'Validation Error',
        },
    },
    'deprecated': True,
}

PROACTIVITY_RESERVATION_OPENAPI = {
    'parameters': [
        {
            'in': 'header',
            'name': 'authorization',
            'required': False,
            'schema': {'title': 'Authorization', 'type': 'string'},
        },
        {
            'in': 'header',
            'name': 'X-App-Platform',
            'required': False,
            'schema': {'title': 'X-App-Platform', 'type': 'string'},
        },
        {
            'in': 'header',
            'name': 'X-Device-Id-Hash',
            'required': False,
            'schema': {'title': 'X-Device-Id-Hash', 'type': 'string'},
        },
        {
            'in': 'header',
            'name': 'X-App-Version',
            'required': False,
            'schema': {'title': 'X-App-Version', 'type': 'string'},
        },
    ],
    'requestBody': {
        'content': {
            'application/json': {
                'schema': {
                    'additionalProperties': False,
                    'properties': {
                        'account_generation': {'minimum': 0.0, 'title': 'Account ' 'Generation', 'type': 'integer'},
                        'candidate_id': {'pattern': '^[0-9a-f]{64}$', 'title': 'Candidate ' 'Id', 'type': 'string'},
                        'device_id': {'pattern': '^[0-9a-f]{64}$', 'title': 'Device ' 'Id', 'type': 'string'},
                        'event_id': {'pattern': '^[0-9a-f]{64}$', 'title': 'Event Id', 'type': 'string'},
                        'operation': {
                            'enum': ['planned_notification', 'ambient_notification', 'nano_triage', 'full_turn'],
                            'title': 'Operation',
                            'type': 'string',
                        },
                        'parent_event_id': {
                            'anyOf': [{'pattern': '^[0-9a-f]{64}$', 'type': 'string'}, {'type': 'null'}],
                            'title': 'Parent ' 'Event ' 'Id',
                        },
                        'trigger_memory_id': {
                            'anyOf': [
                                {'maxLength': 256, 'minLength': 1, 'pattern': '^[^/]+$', 'type': 'string'},
                                {'type': 'null'},
                            ],
                            'title': 'Trigger ' 'Memory ' 'Id',
                        },
                        'trigger_revision': {
                            'anyOf': [{'minimum': 1.0, 'type': 'integer'}, {'type': 'null'}],
                            'title': 'Trigger ' 'Revision',
                        },
                    },
                    'required': ['event_id', 'candidate_id', 'operation', 'account_generation', 'device_id'],
                    'title': 'JITProactivityReservationRequest',
                    'type': 'object',
                }
            }
        },
        'required': True,
    },
    'responses': {
        '200': {
            'content': {
                'application/json': {
                    'schema': {
                        'additionalProperties': False,
                        'properties': {
                            'receipt': {
                                'additionalProperties': False,
                                'properties': {
                                    'account_generation': {
                                        'minimum': 0.0,
                                        'title': 'Account ' 'Generation',
                                        'type': 'integer',
                                    },
                                    'budget_day': {
                                        'pattern': '^\\d{4}-\\d{2}-\\d{2}$',
                                        'title': 'Budget ' 'Day',
                                        'type': 'string',
                                    },
                                    'budget_timezone': {
                                        'default': 'UTC',
                                        'maxLength': 64,
                                        'minLength': 1,
                                        'title': 'Budget ' 'Timezone',
                                        'type': 'string',
                                    },
                                    'candidate_id': {'title': 'Candidate ' 'Id', 'type': 'string'},
                                    'created_at': {'format': 'date-time', 'title': 'Created ' 'At', 'type': 'string'},
                                    'device_id': {'title': 'Device ' 'Id', 'type': 'string'},
                                    'event_id': {'title': 'Event ' 'Id', 'type': 'string'},
                                    'feedback_id': {
                                        'anyOf': [{'type': 'string'}, {'type': 'null'}],
                                        'title': 'Feedback ' 'Id',
                                    },
                                    'operation': {
                                        'enum': [
                                            'planned_notification',
                                            'ambient_notification',
                                            'nano_triage',
                                            'full_turn',
                                        ],
                                        'title': 'Operation',
                                        'type': 'string',
                                    },
                                    'parent_event_id': {
                                        'anyOf': [{'pattern': '^[0-9a-f]{64}$', 'type': 'string'}, {'type': 'null'}],
                                        'title': 'Parent ' 'Event ' 'Id',
                                    },
                                    'request_hash': {
                                        'pattern': '^[0-9a-f]{64}$',
                                        'title': 'Request ' 'Hash',
                                        'type': 'string',
                                    },
                                    'schema_version': {
                                        'const': 'jit_proactivity_event.v1',
                                        'default': 'jit_proactivity_event.v1',
                                        'title': 'Schema ' 'Version',
                                        'type': 'string',
                                    },
                                    'trigger_memory_id': {
                                        'anyOf': [{'type': 'string'}, {'type': 'null'}],
                                        'title': 'Trigger ' 'Memory ' 'Id',
                                    },
                                    'trigger_revision': {
                                        'anyOf': [{'minimum': 1.0, 'type': 'integer'}, {'type': 'null'}],
                                        'title': 'Trigger ' 'Revision',
                                    },
                                    'uid': {'title': 'Uid', 'type': 'string'},
                                },
                                'required': [
                                    'uid',
                                    'event_id',
                                    'candidate_id',
                                    'operation',
                                    'account_generation',
                                    'budget_day',
                                    'device_id',
                                    'created_at',
                                    'request_hash',
                                ],
                                'title': 'JITProactivityEventReceipt',
                                'type': 'object',
                            },
                            'reserved': {'title': 'Reserved', 'type': 'boolean'},
                        },
                        'required': ['reserved', 'receipt'],
                        'title': 'JITProactivityReservationEnvelope',
                        'type': 'object',
                    }
                }
            },
            'description': 'Historical success schema only. This retired endpoint always returns ' '410.',
        },
        '401': {
            'content': {
                'application/json': {
                    'schema': {
                        'properties': {
                            'detail': {
                                'anyOf': [{'type': 'string'}, {'type': 'array'}, {'type': 'object'}],
                                'description': 'Error ' 'detail ' 'returned ' 'by ' 'the ' 'API.',
                            }
                        },
                        'required': ['detail'],
                        'title': 'ErrorResponse',
                        'type': 'object',
                    }
                }
            },
            'description': 'Missing or invalid authentication credentials.',
        },
        '422': {
            'content': {
                'application/json': {
                    'schema': {
                        'properties': {
                            'detail': {
                                'items': {
                                    'properties': {
                                        'loc': {
                                            'items': {'anyOf': [{'type': 'string'}, {'type': 'integer'}]},
                                            'title': 'Location',
                                            'type': 'array',
                                        },
                                        'msg': {'title': 'Message', 'type': 'string'},
                                        'type': {'title': 'Error ' 'Type', 'type': 'string'},
                                    },
                                    'required': ['loc', 'msg', 'type'],
                                    'title': 'ValidationError',
                                    'type': 'object',
                                },
                                'title': 'Detail',
                                'type': 'array',
                            }
                        },
                        'title': 'HTTPValidationError',
                        'type': 'object',
                    }
                }
            },
            'description': 'Validation Error',
        },
    },
    'deprecated': True,
}
