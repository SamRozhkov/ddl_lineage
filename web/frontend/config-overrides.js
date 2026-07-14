module.exports = function override(config /*, env*/) {
    return {
        ...config,
        ignoreWarnings: [
            ...(config.ignoreWarnings || []),
            {
                module: /node_modules\/sql-formatter/,
                message: /Failed to parse source map/,
            },
        ],
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
