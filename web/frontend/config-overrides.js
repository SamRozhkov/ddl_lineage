module.exports = function override(config /*, env*/) {
    return {
        ...config,
        resolve: {
            ...config.resolve,
            plugins: (config.resolve.plugins || []).filter(
                (plugin) => plugin.constructor.name !== 'ModuleScopePlugin',
            ),
        },
        module: {
            ...config.module,
            rules: [
                ...config.module.rules.map((rule) => {
                    if (rule.oneOf) {
                        return {
                            ...rule,
                            oneOf: [
                                {
                                    test: /icons\/.*\.svg$/,
                                    loader: 'svg-inline-loader',
                                },
                                ...rule.oneOf,
                            ],
                        };
                    }
                    return rule;
                }),
            ],
        },
    };
};
