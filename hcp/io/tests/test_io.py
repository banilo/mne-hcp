import shutil
import os
import os.path as op

import numpy as np

from numpy.testing import assert_array_equal
from nose.tools import assert_equal, assert_true, assert_raises


import mne
import hcp
from mne.utils import _TempDir
from hcp.tests import config as tconf
from hcp.tests.config import expensive_test


hcp_params = dict(hcp_path=tconf.hcp_path,
                  subject=tconf.test_subject)


def test_read_annot():
    """testing annotations"""
    for run_index in tconf.run_inds:
        annots = hcp.io.read_annot_hcp(data_type='rest', run_index=run_index,
                                       **hcp_params)
        # channels
        assert_equal(list(sorted(annots['channels'])),
                     ['all', 'ica', 'manual',  'neigh_corr',
                      'neigh_stdratio'])
        for channels in annots['channels'].values():
            for chan in channels:
                assert_true(chan in tconf.bti_chans)

        # segments
        assert_equal(list(sorted(annots['ica'])),
                     ['bad', 'brain_ic', 'brain_ic_number',
                      'brain_ic_vs', 'brain_ic_vs_number',
                      'ecg_eog_ic', 'flag', 'good',
                      'physio', 'total_ic_number'])
        for components in annots['ica'].values():
            if len(components) > 0:
                assert_true(min(components) >= 0)
                assert_true(max(components) <= 248)


def _basic_raw_checks(raw):
    """helper for testing raw files """
    picks = mne.pick_types(raw.info, meg=True, ref_meg=False)
    assert_equal(len(picks), 248)
    ch_names = [raw.ch_names[pp] for pp in picks]
    assert_true(all(ch.startswith('A') for ch in ch_names))
    ch_sorted = list(sorted(ch_names))
    assert_true(ch_sorted != ch_names)
    assert_equal(np.round(raw.info['sfreq'], 4),
                 tconf.sfreq_raw)


def test_read_raw_rest():
    """Test reading raw for resting state"""
    for run_index in tconf.run_inds[:tconf.max_runs]:
        raw = hcp.io.read_raw_hcp(data_type='rest', run_index=run_index,
                                  **hcp_params)
        _basic_raw_checks(raw=raw)


@expensive_test
def test_read_raw_task():
    """Test reading raw for tasks"""
    for run_index in tconf.run_inds[:tconf.max_runs]:
        for data_type in tconf.task_types:
            if run_index == 2:
                assert_raises(
                    ValueError, hcp.io.read_raw_hcp,
                    data_type=data_type, run_index=run_index, **hcp_params)
                continue
            raw = hcp.io.read_raw_hcp(
                data_type=data_type, run_index=run_index, **hcp_params)
            _basic_raw_checks(raw=raw)


@expensive_test
def test_read_raw_noise():
    """Test reading raw for empty room noise"""
    for run_index in tconf.run_inds[:tconf.max_runs][:2]:
        for data_type in tconf.noise_types:
            if run_index == 1:
                assert_raises(
                    ValueError, hcp.io.read_raw_hcp,
                    data_type=data_type, run_index=run_index, **hcp_params)
                continue
            raw = hcp.io.read_raw_hcp(
                data_type=data_type, run_index=run_index, **hcp_params)
            _basic_raw_checks(raw=raw)


def _epochs_basic_checks(epochs, annots, data_type):
    n_good = 248 - len(annots['channels']['all'])
    if data_type == 'task_motor':
        n_good += 4
    assert_equal(len(epochs.ch_names), n_good)
    assert_equal(
        np.round(epochs.info['sfreq'], 2),
        tconf.sfreq_preproc)
    assert_array_equal(
        np.unique(epochs.events[:, 2]),
        np.array([99], dtype=np.int))
    assert_true(
        _check_bounds(epochs.times,
                      tconf.epochs_bounds[data_type])
    )

    # XXX these seem not to be reliably set. checkout later.
    # assert_equal(
    #     epochs.info['lowpass'],
    #     lowpass_preproc)
    # assert_equal(
    #     epochs.info['highpass'],
    #     highpass_preproc)


def test_read_epochs_rest():
    """Test reading epochs for resting state"""
    for run_index in tconf.run_inds[:tconf.max_runs][:2]:
        annots = hcp.io.read_annot_hcp(
            data_type='rest', run_index=run_index, **hcp_params)

        epochs = hcp.io.read_epochs_hcp(
            data_type='rest', run_index=run_index, **hcp_params)

        _epochs_basic_checks(epochs, annots, data_type='rest')


def test_read_epochs_task():
    """Test reading epochs for task"""
    for run_index in tconf.run_inds[:tconf.max_runs][:2]:
        for data_type in tconf.task_types:
            annots = hcp.io.read_annot_hcp(
                data_type=data_type, run_index=run_index, **hcp_params)

            epochs = hcp.io.read_epochs_hcp(
                data_type=data_type, run_index=run_index, **hcp_params)

            _epochs_basic_checks(epochs, annots, data_type)


def _check_bounds(array, bounds):
    """helper for bounds checking"""
    is_in = True
    if not np.allclose(np.min(array), min(bounds), atol=0.01):
        is_in = False
    elif not np.allclose(np.max(array), max(bounds), atol=0.01):
        is_in = False
    return is_in


def test_read_evoked():
    """test reading evokeds """
    for data_type in tconf.task_types:
        all_annots = list()
        for run_index in tconf.run_inds[:2]:
            annots = hcp.io.read_annot_hcp(
                data_type=data_type, run_index=run_index, **hcp_params)
            all_annots.append(annots)

        evokeds = hcp.io.read_evokeds_hcp(data_type=data_type,
                                          kind='average', **hcp_params)

        n_average = sum(ee.kind == 'average' for ee in evokeds)
        assert_equal(n_average, len(evokeds))

        n_chans = 248
        if data_type == 'task_motor':
            n_chans += 4
        n_chans -= len(set(sum(
            [an['channels']['all'] for an in all_annots], [])))
        assert_equal(n_chans, len(evokeds[0].ch_names))
        assert_true(
            _check_bounds(evokeds[0].times,
                          tconf.epochs_bounds[data_type])
        )


def test_read_info():
    """test reading info"""
    tempdir = _TempDir()
    for data_type in tconf.task_types:
        for run_index in tconf.run_inds[:tconf.max_runs][:2]:
            # with pdf file
            info = hcp.io.read_info_hcp(
                data_type=data_type, run_index=run_index, **hcp_params)
            assert_equal(
                {k for k in info['ch_names'] if k.startswith('A')},
                tconf.bti_chans
            )
            # without pdf file
            # in this case the hcp code guesses certain channel labels
            cp_paths = hcp.io.file_mapping.get_file_paths(
                subject=tconf.test_subject, data_type=data_type,
                run_index=run_index, output='raw', hcp_path='',
            )
            for pp in cp_paths:
                if 'c,' in pp:  # don't copy pdf
                    continue
                os.makedirs(op.join(tempdir, op.dirname(pp)))
                shutil.copy(op.join(tconf.hcp_path, pp), op.join(tempdir, pp))

            info2 = hcp.io.read_info_hcp(
                subject=tconf.test_subject, data_type=data_type,
                hcp_path=tempdir,
                run_index=run_index)
            if os.getenv('MNE_HCP_CHEAP', False):
                assert_true(len(info['chs']) == len(info2['chs']))
            else:
                assert_true(len(info['chs']) != len(info2['chs']))
            common_chs = [ch for ch in info2['ch_names'] if
                          ch in info['ch_names']]
            assert_equal(len(common_chs), len(info['chs']))
            info2 = hcp.io.read._hcp_pick_info(info2, common_chs)
            assert_equal(info['ch_names'], info2['ch_names'])
            for ch1, ch2 in zip(info['chs'], info2['chs']):
                assert_array_equal(ch1['loc'], ch2['loc'])


def test_read_trial_info():
    """Test trial info basics"""
    for data_type in tconf.task_types:
        for run_index in tconf.run_inds[:tconf.max_runs][:2]:
            trial_info = hcp.io.read_trial_info_hcp(
                data_type=data_type, run_index=run_index, **hcp_params)
            assert_true('stim' in trial_info)
            assert_true('resp' in trial_info)
            assert_equal(2, len(trial_info))
            for key, val in trial_info.items():
                assert_array_equal(np.ndim(val['comments']), 1)
                assert_array_equal(np.ndim(val['codes']), 2)
