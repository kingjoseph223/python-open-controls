# Copyright 2020 Q-CTRL Pty Ltd & Q-CTRL Inc
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Module for converting dynamical decoupling sequences to driven controls.
"""

import numpy as np

from ..driven_controls import (
    UPPER_BOUND_DETUNING_RATE,
    UPPER_BOUND_RABI_RATE,
)
from ..driven_controls.driven_control import DrivenControl
from ..exceptions import ArgumentsValueError


def _check_valid_operation(rabi_rotations, detuning_rotations):
    """
    Private method to check if there is a rabi_rotation and detuning rotation at the same
    offset.

    Parameters
    ----------
    rabi_rotations : numpy.ndarray
        Rabi rotations at each offset
    detuning_rotations : numpy.ndarray
        Detuning rotations at each offset

    Returns
    -------
    bool
        Returns True if there is not an instance of rabi rotation and detuning rotation
        at the same offset
    """

    rabi_rotation_index = set(np.where(rabi_rotations > 0.0)[0])
    detuning_rotation_index = set(np.where(detuning_rotations > 0.0)[0])

    check_common_index = rabi_rotation_index.intersection(detuning_rotation_index)

    if check_common_index:
        return False

    return True


def _check_maximum_rotation_rate(maximum_rabi_rate, maximum_detuning_rate):
    """
    Checks if the maximum rabi and detuning rate are within valid limits.

    Parameters
    ----------
    maximum_rabi_rate : float
        Maximum Rabi Rate;
    maximum_detuning_rate : float
        Maximum Detuning Rate;

    Raises
    ------
    ArgumentsValueError
        Raised when an argument is invalid or a valid driven control cannot be
        created from the sequence parameters, maximum rabi rate and maximum detuning
        rate provided.
    """

    # check against global parameters
    if maximum_rabi_rate <= 0.0 or maximum_rabi_rate > UPPER_BOUND_RABI_RATE:
        raise ArgumentsValueError(
            "Maximum rabi rate must be greater than 0 and less or equal to {0}".format(
                UPPER_BOUND_RABI_RATE
            ),
            {"maximum_rabi_rate": maximum_rabi_rate},
            extras={
                "maximum_detuning_rate": maximum_detuning_rate,
                "allowed_maximum_rabi_rate": UPPER_BOUND_RABI_RATE,
            },
        )

    if (
        maximum_detuning_rate <= 0.0
        or maximum_detuning_rate > UPPER_BOUND_DETUNING_RATE
    ):
        raise ArgumentsValueError(
            "Maximum detuning rate must be greater than 0 and less or equal to {0}".format(
                UPPER_BOUND_DETUNING_RATE
            ),
            {"maximum_detuning_rate": maximum_detuning_rate,},
            extras={
                "maximum_rabi_rate": maximum_rabi_rate,
                "allowed_maximum_detuning_rate": UPPER_BOUND_DETUNING_RATE,
            },
        )


def convert_dds_to_driven_control(
    dynamic_decoupling_sequence=None,
    maximum_rabi_rate=2 * np.pi,
    maximum_detuning_rate=2 * np.pi,
    minimum_segment_duration=0.0,
    **kwargs
):
    """
    Creates a Driven Control based on the supplied DDS and other relevant information.

    Currently, pulses that simultaneously contain Rabi and detuning rotations are not
    supported.

    Parameters
    ----------
    dynamic_decoupling_sequence : qctrlopencontrols.DynamicDecouplingSequence
        The base DDS. Its offsets should be sorted in ascending order in time.
    maximum_rabi_rate : float, optional
        Maximum Rabi Rate; Defaults to 2*pi.
        Must be greater than 0 and less or equal to UPPER_BOUND_RABI_RATE, if set.
    maximum_detuning_rate : float, optional
        Maximum Detuning Rate; Defaults to 2*pi.
        Must be greater than 0 and less or equal to UPPER_BOUND_DETUNING_RATE, if set.
    minimum_segment_duration : float, optional
        If set, further restricts the duration of every segment of the Driven Controls.
        Defaults to 0, in which case it does not affect the duration of the pulses.
        Must be greater or equal to 0, if set.
    kwargs : dict, optional
        Options to make the corresponding filter type.
        I.e. the options for primitive are described in doc for the PrimitivePulse class.

    Returns
    -------
    DrivenControls
        The Driven Control that contains the segments
        corresponding to the Dynamic Decoupling Sequence operation.

    Raises
    ------
    ArgumentsValueError
        Raised when an argument is invalid or a valid driven control cannot be
        created from the sequence parameters, maximum rabi rate and maximum detuning
        rate provided.

    Notes
    -----
    Driven pulse is defined as a sequence of control segments. Each segment performs
    an operation (rotation around one or more axes). While the dynamic decoupling
    sequence operation contains ideal instant operations, the maximum Rabi (detuning) rate
    defines a minimum time required to perform a given rotation operation. Therefore, each
    operation in sequence is converted to a flat-topped control segment with a finite duration.
    Each offset is taken as the mid-point of the control segment and the width of the
    segment is determined by (rotation/max_rabi(detuning)_rate).

    If the sequence contains operations at either of the extreme ends
    :math:`\\tau_0=0` and :math:`\\tau_{n+1}=\\tau`(duration of the sequence), there
    will be segments outside the boundary (segments starting before :math:`t<0`
    or finishing after the sequence duration :math:`t>\\tau`). In these cases, the segments
    on either of the extreme ends are shifted appropriately so that their start/end time
    falls entirely within the duration of the sequence.

    Moreover, a check is made to make sure the resulting control segments are non-overlapping.

    If appropriate control segments cannot be created, the conversion process raises
    an ArgumentsValueError.
    """

    if dynamic_decoupling_sequence is None:
        raise ArgumentsValueError(
            "Dynamic decoupling sequence must be of " "DynamicDecoupling type.",
            {"type(dynamic_decoupling_sequence": type(dynamic_decoupling_sequence)},
        )

    if minimum_segment_duration < 0.0:
        raise ArgumentsValueError(
            "Minimum segment duration must be greater or equal to 0.",
            {"minimum_segment_duration": minimum_segment_duration},
        )

    _check_maximum_rotation_rate(maximum_rabi_rate, maximum_detuning_rate)

    sequence_duration = dynamic_decoupling_sequence.duration
    offsets = dynamic_decoupling_sequence.offsets
    rabi_rotations = dynamic_decoupling_sequence.rabi_rotations
    azimuthal_angles = dynamic_decoupling_sequence.azimuthal_angles
    detuning_rotations = dynamic_decoupling_sequence.detuning_rotations

    # check if all Rabi rotations are valid (i.e. have positive values)
    if np.any(np.less(rabi_rotations, 0.0)):
        raise ArgumentsValueError(
            "Sequence contains negative values for Rabi rotations.",
            {"dynamic_decoupling_sequence": str(dynamic_decoupling_sequence)},
        )

    # check for valid operation
    if not _check_valid_operation(
        rabi_rotations=rabi_rotations, detuning_rotations=detuning_rotations
    ):
        raise ArgumentsValueError(
            "Sequence operation includes rabi rotation and "
            "detuning rotation at the same instance.",
            {"dynamic_decoupling_sequence": str(dynamic_decoupling_sequence)},
            extras={
                "maximum_rabi_rate": maximum_rabi_rate,
                "maximum_detuning_rate": maximum_detuning_rate,
            },
        )

    if offsets.size == 0:
        offsets = np.array([0, sequence_duration])
        rabi_rotations = np.array([0, 0])
        azimuthal_angles = np.array([0, 0])
        detuning_rotations = np.array([0, 0])

    if offsets[0] != 0:
        offsets = np.append([0], offsets)
        rabi_rotations = np.append([0], rabi_rotations)
        azimuthal_angles = np.append([0], azimuthal_angles)
        detuning_rotations = np.append([0], detuning_rotations)
    if offsets[-1] != sequence_duration:
        offsets = np.append(offsets, [sequence_duration])
        rabi_rotations = np.append(rabi_rotations, [0])
        azimuthal_angles = np.append(azimuthal_angles, [0])
        detuning_rotations = np.append(detuning_rotations, [0])

    # check that the offsets are correctly sorted in time
    if any(np.diff(offsets) <= 0.0):
        raise ArgumentsValueError(
            "Pulse timing could not be properly deduced from "
            "the sequence offsets. Make sure all offsets are "
            "in increasing order.",
            {"dynamic_decoupling_sequence": dynamic_decoupling_sequence},
            extras={"offsets": offsets},
        )

    offsets = offsets[np.newaxis, :]
    rabi_rotations = rabi_rotations[np.newaxis, :]
    azimuthal_angles = azimuthal_angles[np.newaxis, :]
    detuning_rotations = detuning_rotations[np.newaxis, :]

    operations = np.concatenate(
        (offsets, rabi_rotations, azimuthal_angles, detuning_rotations), axis=0
    )

    pulse_mid_points = operations[0, :]

    pulse_start_ends = np.zeros((operations.shape[1], 2))
    for op_idx in range(operations.shape[1]):
        # Pulses that cause no rotations can have 0 duration
        half_pulse_duration = 0.0

        if not np.isclose(operations[1, op_idx], 0.0):  # Rabi rotation
            half_pulse_duration = 0.5 * max(
                operations[1, op_idx] / maximum_rabi_rate, minimum_segment_duration
            )
        elif not np.isclose(operations[3, op_idx], 0.0):  # Detuning rotation
            half_pulse_duration = 0.5 * max(
                np.abs(operations[3, op_idx]) / maximum_detuning_rate,
                minimum_segment_duration,
            )

        pulse_start_ends[op_idx, 0] = pulse_mid_points[op_idx] - half_pulse_duration
        pulse_start_ends[op_idx, 1] = pulse_mid_points[op_idx] + half_pulse_duration

    # check if any of the pulses have gone outside the time limit [0, sequence_duration]
    # if yes, adjust the segment timing
    if pulse_start_ends[0, 0] < 0.0:
        translation = 0.0 - (pulse_start_ends[0, 0])
        pulse_start_ends[0, :] = pulse_start_ends[0, :] + translation

    if pulse_start_ends[-1, 1] > sequence_duration:
        translation = pulse_start_ends[-1, 1] - sequence_duration
        pulse_start_ends[-1, :] = pulse_start_ends[-1, :] - translation

    # check if the minimum_segment_duration is respected in the gaps between the pulses
    # as minimum_segment_duration >= 0, this also excludes overlaps
    gap_durations = pulse_start_ends[1:, 0] - pulse_start_ends[:-1, 1]
    if not np.all(
        np.logical_or(
            np.greater(gap_durations, minimum_segment_duration),
            np.isclose(gap_durations, minimum_segment_duration),
        )
    ):
        raise ArgumentsValueError(
            "Distance between pulses does not respect minimum_segment_duration. "
            "Try decreasing the minimum_segment_duration or increasing "
            "the maximum_rabi_rate or the maximum_detuning_rate.",
            {
                "dynamic_decoupling_sequence": dynamic_decoupling_sequence,
                "maximum_rabi_rate": maximum_rabi_rate,
                "maximum_detuning_rate": maximum_detuning_rate,
                "minimum_segment_duration": minimum_segment_duration,
            },
            extras={
                "deduced_pulse_start_timing": pulse_start_ends[:, 0],
                "deduced_pulse_end_timing": pulse_start_ends[:, 1],
                "gap_durations": gap_durations,
            },
        )

    if np.allclose(pulse_start_ends, 0.0):
        # the original sequence should be a free evolution
        return DrivenControl(
            rabi_rates=[0.0],
            azimuthal_angles=[0.0],
            detunings=[0.0],
            durations=[sequence_duration],
            **kwargs
        )

    control_rabi_rates = np.zeros((operations.shape[1] * 2,))
    control_azimuthal_angles = np.zeros((operations.shape[1] * 2,))
    control_detunings = np.zeros((operations.shape[1] * 2,))
    control_durations = np.zeros((operations.shape[1] * 2,))

    pulse_segment_idx = 0
    for op_idx in range(0, operations.shape[1]):
        pulse_width = pulse_start_ends[op_idx, 1] - pulse_start_ends[op_idx, 0]
        control_durations[pulse_segment_idx] = pulse_width

        if pulse_width > 0.0:
            if not np.isclose(operations[1, op_idx], 0.0):  # Rabi rotation
                control_rabi_rates[pulse_segment_idx] = (
                    operations[1, op_idx] / pulse_width
                )
                control_azimuthal_angles[pulse_segment_idx] = operations[2, op_idx]
            elif not np.isclose(operations[3, op_idx], 0.0):  # Detuning rotation
                control_detunings[pulse_segment_idx] = (
                    operations[3, op_idx] / pulse_width
                )

        if op_idx != (operations.shape[1] - 1):
            control_rabi_rates[pulse_segment_idx + 1] = 0.0
            control_azimuthal_angles[pulse_segment_idx + 1] = 0.0
            control_detunings[pulse_segment_idx + 1] = 0.0
            control_durations[pulse_segment_idx + 1] = (
                pulse_start_ends[op_idx + 1, 0] - pulse_start_ends[op_idx, 1]
            )

        pulse_segment_idx += 2

    # almost there; let us check if there is any segments with durations = 0
    control_rabi_rates = control_rabi_rates[control_durations > 0.0]
    control_azimuthal_angles = control_azimuthal_angles[control_durations > 0.0]
    control_detunings = control_detunings[control_durations > 0.0]
    control_durations = control_durations[control_durations > 0.0]

    return DrivenControl(
        rabi_rates=control_rabi_rates,
        azimuthal_angles=control_azimuthal_angles,
        detunings=control_detunings,
        durations=control_durations,
        **kwargs
    )
