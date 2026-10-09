module.exports = function override(config /*, env*/) {
    // The webpack ESLint pass keeps CRA's own react-app rules; the project style
    // config (.eslintrc, @gravity-ui/eslint-config) is checked by `npm run lint`
    config.plugins
        .filter((plugin) => plugin.constructor.name === 'ESLintWebpackPlugin')
        .forEach((plugin) => {
            plugin.options.useEslintrc = false;
        });

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
