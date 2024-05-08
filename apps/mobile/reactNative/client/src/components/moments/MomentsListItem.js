import {useContext, useRef} from 'react';
import {ListItem} from 'react-native-elements';
import Swipeable from 'react-native-gesture-handler/Swipeable';
import {TouchableOpacity, StyleSheet, Text} from 'react-native';
import {MomentsContext} from '../../contexts/MomentsContext';
import {FontAwesomeIcon} from '@fortawesome/react-native-fontawesome';
import {faTrash} from '@fortawesome/free-solid-svg-icons';

const MomentListItem = ({momentId, onItemPress}) => {
  const {deleteMoment, moments} = useContext(MomentsContext);
  const swipeableRef = useRef(null);
  const touchableRef = useRef(null);

  const moment = moments.find(moment => moment.momentId === momentId);
  if (!moment) {
    return <Text>Loading moment...</Text>;
  }
  
  const handleDelete = momentId => {
    if (swipeableRef.current) {
      swipeableRef.current.close();
    }
    deleteMoment(momentId);
  };

  const renderRightActions = () => (
    <TouchableOpacity
      onPress={() => handleDelete(momentId)}
      style={styles.deleteButton}>
      <FontAwesomeIcon icon={faTrash} size={30} color="white" />
    </TouchableOpacity>
  );

  const formatDate = date => {
    return new Date(date).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  };

  return (
    <Swipeable
      ref={swipeableRef}
      renderRightActions={renderRightActions}
      friction={2}
      rightThreshold={100}
      simultaneousHandlers={touchableRef}>
      <TouchableOpacity
        ref={touchableRef}
        onPress={() => onItemPress(momentId)}
        activeOpacity={0.6}
        style={styles.touchable}>
        <ListItem
          key={moment.momentId}
          bottomDivider
          containerStyle={styles.listItem}>
          <ListItem.Content>
            <ListItem.Title>
              {moment.title.substring(0, 30) + '...'}
            </ListItem.Title>
            <ListItem.Subtitle>{formatDate(moment.date)}</ListItem.Subtitle>
          </ListItem.Content>
          <ListItem.Chevron />
        </ListItem>
      </TouchableOpacity>
    </Swipeable>
  );
};

const styles = StyleSheet.create({
  listItem: {
    backgroundColor: '#f9f9f9',
    borderRadius: 10,
    marginVertical: 8,
    overflow: 'hidden',
  },
  touchable: {
    flex: 1,
    marginHorizontal: 10, // Side margins for better spacing
  },
  deleteButton: {
    backgroundColor: 'red',
    justifyContent: 'center',
    alignItems: 'center',
    width: 70,
    height: 'auto',
    marginVertical: 8,
    borderRadius: 10,
  },
});

export default MomentListItem;
