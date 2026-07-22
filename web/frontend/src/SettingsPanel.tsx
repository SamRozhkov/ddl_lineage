import {Globe} from '@gravity-ui/icons';
import {Icon, SegmentedRadioGroup} from '@gravity-ui/uikit';
import React from 'react';

import {getAvailableLanguages, useI18n} from './i18n';

export const SettingsPanel: React.FC = () => {
    const {lang, setLang, t} = useI18n();
    const languages = getAvailableLanguages();

    return (
        <div className="side-panel">
            <div className="side-panel__header">
                <h3>{t('settings.title')}</h3>
            </div>

            <div className="side-panel__body">
                <div className="side-panel__section">
                    <div className="side-panel__section-title">
                        <Icon data={Globe} size={13} />
                        {t('settings.language')}
                    </div>
                    <SegmentedRadioGroup value={lang} onUpdate={setLang} width="max">
                        {languages.map(({code, name}) => (
                            <SegmentedRadioGroup.Option key={code} value={code}>
                                {name}
                            </SegmentedRadioGroup.Option>
                        ))}
                    </SegmentedRadioGroup>
                </div>
            </div>
        </div>
    );
};
